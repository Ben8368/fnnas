// SPDX-License-Identifier: GPL-2.0-only
/* Umi wireless USBIN only. LOS 71b13e62 NuVolta (colin) and Qualcomm SMB5.
 * EPP alone never charges the battery. The opt-in buck build adds guarded
 * SMB5 battery control only; neither build requests PD, FFC or wireless CP.
 */
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/gpio/consumer.h>
#include <linux/pinctrl/consumer.h>
#include "qcom_pm8150b_internal.h"
#include "qcom_pm8150b_rx.h"
#include "umi_rx_thermal.h"

enum { ICL, FCC, ADAPTER, RANGE, OPTIONS, OVERRIDE, LOAD, AICL, INPUT,
#ifdef CONFIG_UMI_RX_BUCK
	FV, TERM_MODE, TERM_HI_M, TERM_HI_L, TERM_LO_M, TERM_LO_L,
#endif
	NREG };
static const struct { u16 offset; u8 mask; } fields[NREG] = {
	[ICL] = {USBIN_CURRENT_LIMIT_CFG, 0xff}, [FCC] = {FAST_CHARGE_CURRENT_CFG, 0xff},
	[ADAPTER] = {0x344, 0xff}, [RANGE] = {USBIN_ADAPTER_ALLOW_CFG, USBIN_ADAPTER_ALLOW_MASK},
	[OPTIONS] = {USBIN_ICL_OPTIONS, USBIN_MODE_CHG_BIT}, [OVERRIDE] = {CMD_ICL_OVERRIDE, ICL_OVERRIDE_BIT},
	[LOAD] = {USBIN_LOAD_CFG, ICL_OVERRIDE_AFTER_APSD_BIT}, [AICL] = {USBIN_AICL_OPTIONS_CFG, USBIN_AICL_EN_BIT},
#ifdef CONFIG_UMI_RX_BUCK
	[FV] = {FLOAT_VOLTAGE_CFG, 0xff}, [TERM_MODE] = {0x6c, BIT(0)},
	[TERM_HI_M] = {0x67, 0xff}, [TERM_HI_L] = {0x68, 0xff},
	[TERM_LO_M] = {0x69, 0xff}, [TERM_LO_L] = {0x6a, 0xff},
#endif
	[INPUT] = {USBIN_CMD_IL, USBIN_SUSPEND_BIT},
};

struct umi_rx_epp {
	struct regmap *divider;
	struct gpio_desc *pump, *q1, *sw, *pass, *hw_sleep;
	struct iio_channel *therm[5];
	unsigned int saved[NREG];
	unsigned int touched;
	bool dirty, epp, fault;
#ifdef CONFIG_UMI_RX_BUCK
	bool preselect, calibrated, identified;
	int six_idx, taper_count;
	unsigned long next_taper, deadline;
#endif
	int epoch, request, mode, capability, adapter, step;
};

int umi_rx_epp_attach(struct smb5_chip *c)
{
	static const char * const names[] = {"cam_therm1", "conn_therm", "quiet_therm", "wireless_therm", "xo_therm"};
	struct umi_rx_epp *s;
	struct i2c_client *ln;
	struct device_node *node;
	struct pinctrl *pins;
	int i;

	s = devm_kzalloc(c->dev, sizeof(*s), GFP_KERNEL);
	if (!s) return -ENOMEM;
	node = of_parse_phandle(c->dev->of_node, "qcom,wireless-divider", 0);
	if (!node || !of_device_is_compatible(node, "xiaomi,umi-ln8282")) {
		of_node_put(node);
		return -EINVAL;
	}
	ln = of_find_i2c_device_by_node(node);
	of_node_put(node);
	if (!ln) return -EPROBE_DEFER;
	device_lock(&ln->dev);
	if (device_is_bound(&ln->dev) && device_link_add(c->dev, &ln->dev, DL_FLAG_AUTOREMOVE_CONSUMER))
		s->divider = dev_get_regmap(&ln->dev, NULL);
	device_unlock(&ln->dev);
	put_device(&ln->dev);
	if (!s->divider) return -EPROBE_DEFER;
	for (i = 0; i < ARRAY_SIZE(names); i++) {
		s->therm[i] = devm_iio_channel_get(c->dev, names[i]);
		if (IS_ERR(s->therm[i])) return PTR_ERR(s->therm[i]);
	}
	pins = devm_pinctrl_get_select(c->dev, "rx-pump-off");
	if (IS_ERR(pins)) return PTR_ERR(pins);
	s->pump = devm_gpiod_get(c->dev, "wireless-pump", GPIOD_OUT_LOW);
	if (IS_ERR(s->pump)) return PTR_ERR(s->pump);
	i = gpiod_get_value_cansleep(s->pump);
	if (i) return i < 0 ? i : -EIO;
	s->q1 = devm_gpiod_get(c->dev, "wireless-q1", GPIOD_OUT_LOW);
	if (IS_ERR(s->q1)) return PTR_ERR(s->q1);
	s->pass = devm_gpiod_get(c->dev, "wireless-pass", GPIOD_OUT_LOW);
	if (IS_ERR(s->pass)) return PTR_ERR(s->pass);
	s->sw = devm_gpiod_get(c->dev, "wireless-switch", GPIOD_OUT_HIGH);
	if (IS_ERR(s->sw)) return PTR_ERR(s->sw);
	/* LOS holds TLMM78 high throughout HLOS, not the active-low TLMM155. */
	s->hw_sleep = devm_gpiod_get(c->dev, "wireless-hw-sleep", GPIOD_OUT_HIGH);
	if (IS_ERR(s->hw_sleep)) return PTR_ERR(s->hw_sleep);
	if (gpiod_get_value_cansleep(s->q1) != 0 || gpiod_get_value_cansleep(s->pass) != 0 ||
	    gpiod_get_value_cansleep(s->sw) != 1 || gpiod_get_value_cansleep(s->hw_sleep) != 1)
		return -EIO;
	c->epp = s;
	return 0;
}

bool umi_rx_epp_fault(struct smb5_chip *c)
{
	return c->epp && c->epp->fault;
}

void umi_rx_epp_latch(struct smb5_chip *c)
{
	/* Dropping enable may itself toggle PG: it is not proof of removal. */
	if (c->epp) c->epp->fault = true;
}

bool umi_rx_epp_owned(struct smb5_chip *c)
{
	return c->epp && READ_ONCE(c->epp->dirty);
}

static int rx_pin(struct gpio_desc *pin, bool on)
{
	int ret = gpiod_direction_output(pin, on);

	if (!ret) ret = gpiod_get_value_cansleep(pin);
	return ret < 0 ? ret : ret == on ? 0 : -EIO;
}

static int rx_guard(void *ctx)
{
	struct smb5_chip *c = ctx;
	int ret;

	if (c->epp->fault || c->stopping || c->stop_pending || c->pps_owned || c->pps_fault || c->inhibit ||
	    c->cooling_state || c->pd_transition || c->epp->epoch != umi_rx1619_epoch(c->wireless_rx))
		return -ENOLINK;
	if (gpiod_get_value_cansleep(c->epp->sw) != 1 ||
	    gpiod_get_value_cansleep(c->epp->pass) != 0 ||
	    gpiod_get_value_cansleep(c->epp->hw_sleep) != 1) return -EIO;
	ret = gpiod_get_value_cansleep(c->epp->pump);
	if (ret) return ret < 0 ? ret : -EBUSY;
#ifdef CONFIG_UMI_RX_BUCK
	ret = umi_rx_buck_charge_state(c);
#else
	ret = smb5_rx_diag_check_off(c);
#endif
	if (ret) return ret;
#ifdef CONFIG_UMI_RX_BUCK
	if (c->epp->preselect) {
		ret = smb5_rx_cable(c);
		if (ret) return ret < 0 ? ret : -EBUSY;
		ret = smb5_wireless_rx_state(c);
		if (ret != 1) return ret < 0 ? ret : -ENOLINK;
		return c->epp->epoch == umi_rx1619_epoch(c->wireless_rx) ? 0 : -ENOLINK;
	}
#endif
	ret = smb5_usbin_owner(c);
	if (ret != SMB5_INPUT_RX) return ret < 0 ? ret : -ENOLINK;
	return c->epp->epoch == umi_rx1619_epoch(c->wireless_rx) ? 0 : -ENOLINK;
}

static int rx_field(struct smb5_chip *c, int idx, unsigned int val, bool restoring)
{
	unsigned int reg = c->base + fields[idx].offset, mask = fields[idx].mask, actual;
	int ret = restoring ? 0 : rx_guard(c);

	if (!ret) {
		/* A failed transfer or readback can still leave a completed write. */
		if (!restoring) c->epp->touched |= BIT(idx);
		ret = regmap_update_bits(c->regmap, reg, mask, val);
	}
	if (!ret) ret = regmap_read(c->regmap, reg, &actual);
	if (ret) {
		dev_warn_ratelimited(c->dev, "wireless RX %s reg=%#x mask=%#x rc=%d\n",
				     restoring ? "restore" : "configure", reg, mask, ret);
		return ret;
	}
	if ((actual & mask) == (val & mask)) return 0;
	dev_warn_ratelimited(c->dev, "wireless RX %s readback reg=%#x mask=%#x want=%#x got=%#x\n",
			     restoring ? "restore" : "configure", reg, mask, val & mask, actual & mask);
	return -EIO;
}

static int rx_begin(struct smb5_chip *c, int epoch)
{
	struct umi_rx_epp *s = c->epp;
	int i, ret;

	if (s->dirty) return -EPROTO;
	s->epoch = epoch;
	ret = rx_guard(c);
	if (ret) return ret;
	for (i = 0; i < NREG; i++) {
		ret = regmap_read(c->regmap, c->base + fields[i].offset, &s->saved[i]);
		if (ret) {
			dev_warn_ratelimited(c->dev, "wireless RX save reg=%#x rc=%d\n",
					     c->base + fields[i].offset, ret);
			return ret;
		}
	}
	if (s->saved[ICL] * CURRENT_SCALE_FACTOR > UMI_CHARGE_USB_ICL_UA ||
	    s->saved[FCC] * CURRENT_SCALE_FACTOR > UMI_CHARGE_FCC_UA ||
	    (s->saved[INPUT] & USBIN_SUSPEND_BIT)) return -EPERM;
#ifdef CONFIG_UMI_RX_BUCK
	s->six_idx = -1;
	s->taper_count = 0;
	s->calibrated = s->identified = false;
#endif
	s->request = s->mode = s->step = s->adapter = 0;
	/* A charger-stop fallback can suspend USBIN outside rx_field(). */
	s->touched = BIT(INPUT);
	WRITE_ONCE(s->dirty, true);
	return 0;
}

int umi_rx_epp_release(struct smb5_chip *c)
{
	int i, ret, pump, pass, sw, q1, isolate;

#ifdef CONFIG_UMI_RX_BUCK
	int pre_pg, pre_cable;
#endif
	if (!umi_rx_epp_owned(c)) return 0;
#ifdef CONFIG_UMI_RX_BUCK
	pre_pg = smb5_wireless_rx_state(c);
	pre_cable = smb5_rx_cable(c);
	ret = smb5_inhibit_with_fallback(c, "wireless-buck-stop");
	WRITE_ONCE(c->rx_buck_active, false);
	c->epp->preselect = false;
	/* Even if the charger did not stop, isolate RX; retry before restore. */
#endif
	pump = rx_pin(c->epp->pump, false);
	/* Sink-only branch of smblib_set_wirless_power_good_enable(false).
	 * Attempt every isolating action even if an earlier GPIO read failed. */
	pass = rx_pin(c->epp->pass, false);
	msleep(50);
	sw = gpiod_get_value_cansleep(c->epp->sw);
	if (sw != 1) {
		sw = rx_pin(c->epp->sw, true);
		msleep(50);
	} else {
		sw = 0;
	}
	q1 = rx_pin(c->epp->q1, false);
#ifdef CONFIG_UMI_RX_BUCK
	if (!ret)
#endif
		ret = smb5_inhibit_with_fallback(c, "wireless-release");
	isolate = umi_rx1619_pin(c->wireless_rx, false);
	if (ret || pump || pass || sw || q1 || isolate) {
		dev_warn_ratelimited(c->dev,
			"wireless RX isolate epoch=%d stop=%d pump=%d pass=%d switch=%d q1=%d receiver=%d\n",
			c->epp->epoch, ret, pump, pass, sw, q1, isolate);
		return ret ?: pump ?: pass ?: sw ?: q1 ?: isolate;
	}
	/* First withdraw the override; restore the old current ceiling last.
	 * Failed cleanup retains ownership and prevents all wired entry points.
	 */
	for (i = NREG - 1; i >= 0; i--) {
		if (!(c->epp->touched & BIT(i))) continue;
		ret = rx_field(c, i, c->epp->saved[i], true);
		if (ret) return ret;
	}
#ifdef CONFIG_UMI_RX_BUCK
	dev_info(c->dev, "umi-rx-buck-stop epoch=%d charge_off=1 route_off=1 restored=1 entry_pg=%d entry_cable=%d\n",
		 c->epp->epoch, pre_pg, pre_cable);
#endif
	WRITE_ONCE(c->epp->dirty, false);
	return 0;
}

int umi_rx_epp_poll(struct smb5_chip *c)
{
	struct umi_rx_epp *s = c->epp;
	union power_supply_propval v;
	unsigned int mode;
	int t[6], i, rc, level, icl, fcc;

	if (!s || !s->dirty) return 0;
	rc = rx_guard(c);
	if (!rc && s->mode > 0 && gpiod_get_value_cansleep(s->q1) != 1) rc = -EIO;
	if (!rc && s->mode > 0) {
		rc = regmap_read(s->divider, 0x0f, &mode);
		if (!rc && (mode & 3) != s->mode) rc = -ENOLINK;
	}
	if (!rc) rc = power_supply_get_property(c->bms, POWER_SUPPLY_PROP_TEMP, &v);
	if (rc) return rc;
	if (v.intval <= -400 || v.intval >= 1250) return -ERANGE;
	t[0] = v.intval * 100;
	for (i = 0; i < ARRAY_SIZE(s->therm); i++) {
		rc = iio_read_channel_processed(s->therm[i], &t[i + 1]);
		if (rc < 0) return rc;
	}
	level = umi_rx_level(&s->step, t, -1);
	if (level < 0) return level;
	rc = umi_rx_caps(s->adapter, s->epp, level, &icl, &fcc);
	if (rc) return rc;
	icl = min(s->request, icl ?: s->request);
	icl = min_t(unsigned int, icl, s->saved[ICL] * CURRENT_SCALE_FACTOR);
	fcc = min_t(unsigned int, fcc ?: UMI_CHARGE_FCC_UA, s->saved[FCC] * CURRENT_SCALE_FACTOR);
#ifdef CONFIG_UMI_RX_BUCK
	/* Limit the first buck-only run to the LOS switching-mode 600 mA step.
	 * Stay below the LOS non-verified FCC ceiling without touching FFC. */
	icl = min(icl, 600000);
	fcc = min(fcc, 2000000);
	/* Keep thermal validation ahead of divider switching, but do not
	 * program limits before the arbiter qualifies the shared input. */
	if (s->preselect)
		return 0;
#endif
	rc = rx_field(c, FCC, fcc / CURRENT_SCALE_FACTOR, false);
	return rc ?: rx_field(c, ICL, icl / CURRENT_SCALE_FACTOR, false);
}

static int rx_budget(struct smb5_chip *c, int ua)
{
	int ret;

	c->epp->request = ua;
	ret = umi_rx_epp_poll(c);
#ifdef CONFIG_UMI_RX_BUCK
	if (c->epp->preselect)
		return ret;
#endif
	if (!ret) ret = rx_field(c, OPTIONS, USBIN_MODE_CHG_BIT, false);
	if (!ret) ret = rx_field(c, OVERRIDE, ICL_OVERRIDE_BIT, false);
	if (!ret) ret = rx_field(c, LOAD, ICL_OVERRIDE_AFTER_APSD_BIT, false);
	if (!ret) ret = rx_field(c, INPUT, 0, false);
	if (!ret) ret = rx_guard(c);
	/* LOS RERUN_AICL is a command bit, not a persistent setting. */
	return ret ?: regmap_write_bits(c->regmap, c->base + 0x644, BIT(0), BIT(0));
}

#ifdef CONFIG_UMI_RX_BUCK
#include "umi_rx_buck.h"
#endif

int umi_rx_epp_event(void *ctx, unsigned int cmd, unsigned int value, int epoch)
{
	struct smb5_chip *c = ctx;
	struct umi_rx_epp *s = c->epp;
	int ret;

	if (!s) return -ENODEV;
	if (cmd == 1) {
#ifdef CONFIG_UMI_RX_BUCK
		ret = s->dirty && !s->request && s->epoch == epoch ? rx_guard(c) : -EPROTO;
#else
		ret = rx_begin(c, epoch);
#endif
		if (ret) return ret;
		s->epp = value & 0x80;
		s->capability = value & 0x7f;
		ret = rx_budget(c, s->epp ? 30000 : 200000);
		if (!ret) ret = rx_guard(c);
		if (!ret) ret = rx_pin(s->q1, true);
		if (!ret) ret = rx_field(c, ADAPTER, 0, false);
		if (!ret) ret = rx_field(c, RANGE, 0x0c, false);
		if (ret || !s->epp) return ret;
		s->mode = umi_ln_forward(s->divider, rx_guard, c);
		if (s->mode < 0) return s->mode;
		msleep(50);
		ret = rx_budget(c, s->mode == 2 ? 600000 : 300000);
		if (ret) return ret;
		msleep(50);
		ret = rx_budget(c, s->mode == 2 ? 1400000 : 700000);
		if (!ret) msleep(50);
		return ret;
	}
	if (!s->dirty || s->epoch != epoch) return -EPROTO;
	switch (cmd) {
	case 2: return rx_field(c, AICL, 0, false);
	case 3:
#ifdef CONFIG_UMI_RX_BUCK
		if (s->calibrated) return -EPROTO;
		s->calibrated = true;
#endif
		ret = rx_field(c, AICL, USBIN_AICL_EN_BIT, false);
		if (ret || !s->epp || s->capability != 10) return ret;
		return rx_budget(c, s->mode == 2 ? 1800000 : 900000);
	case 6:
#ifdef CONFIG_UMI_RX_BUCK
		if (s->epp && value >= 9 && value <= 16) {
			int term_ma;

			ret = rx_guard(c);
			if (!ret) ret = umi_fg_loaded_profile(c->bms, &term_ma);
			if (ret) return ret;
			dev_info(c->dev, "RX loaded FG profile ffc_term_ma=%d (not enabled) epoch=%d\n",
				 term_ma, epoch);
		}
		s->identified = s->epp && value >= 9 && value <= 16;
#endif
		s->adapter = value;
		return umi_rx_epp_poll(c);
	default: return -EINVAL;
	}
}
