/* SPDX-License-Identifier: GPL-2.0-only */
/* Umi wireless EPP to PM8150B switch charger, not WLDC, PPS or FFC.
 * Board limits and six-pin steps: Xiaomi/Qualcomm LOS 71b13e62.
 * All operations run in the SMB5 worker under chip->lock. */
int umi_rx_buck_charge_state(struct smb5_chip *c)
{
	int state, ret = smb5_get_prop_charging_enabled(c, &state);
	int expected = c->rx_buck_active ? POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO :
		POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE;

	return ret ?: (state == expected ? 0 : -EBUSY);
}

static int buck_value(struct power_supply *psy, enum power_supply_property prop, int *v)
{
	union power_supply_propval data;
	int rc = power_supply_get_property(psy, prop, &data);

	if (!rc) *v = data.intval;
	return rc;
}

static int buck_pump_off(struct smb5_chip *c)
{
	struct power_supply *pump;
	int state, rc;

	pump = power_supply_get_by_reference(dev_fwnode(c->dev), "qcom,wireless-pump-monitor");
	if (IS_ERR_OR_NULL(pump)) return pump ? PTR_ERR(pump) : -ENODEV;
	rc = buck_value(pump, POWER_SUPPLY_PROP_STATUS, &state);
	power_supply_put(pump);
	return rc ?: (state == POWER_SUPPLY_STATUS_NOT_CHARGING ? 0 : -EBUSY);
}

static int buck_tx_id_guard(void *ctx, bool limit_bpp)
{
	struct smb5_chip *c = ctx;
	unsigned int icl;
	int ret, q1;

	if (!c->epp->preselect || !c->epp->dirty || c->rx_buck_active || limit_bpp)
		return -ENOLINK;
	ret = buck_pump_off(c);
	if (!ret) ret = regmap_read(c->regmap, c->base + USBIN_CURRENT_LIMIT_CFG, &icl);
	if (ret) return ret;
	q1 = gpiod_get_value_cansleep(c->epp->q1);
	if (q1 < 0) return q1;
	if (icl || q1 != 1) {
		dev_warn_ratelimited(c->dev, "wireless RX mailbox interlock icl_raw=%#x q1=%d\n", icl, q1);
		return -EBUSY;
	}
	return rx_guard(c);
}

static int buck_wait_usbin(struct smb5_chip *c)
{
	int i, owner, ret;

	for (i = 0; i <= 50; i++) {
		ret = rx_guard(c);
		if (ret) return ret;
		owner = smb5_usbin_owner(c);
		if (owner == SMB5_INPUT_RX) return 0;
		if (owner != SMB5_INPUT_UNRESOLVED) return owner < 0 ? owner : -ENOLINK;
		if (i < 50) {
			ret = umi_rx1619_preselect_tx_id(c->wireless_rx, c->epp->epoch,
						       buck_tx_id_guard, c);
			if (ret) return ret;
			/* LDO/FOD mailbox replies are what make RX output reach USBIN.
			 * Service them while preselection still holds the battery off. */
			ret = umi_rx1619_preselect_service(c->wireless_rx, buck_tx_id_guard, c);
			if (ret) return ret;
			msleep(10);
		}
	}
	return -ETIMEDOUT;
}

static int buck_read_path(struct smb5_chip *c, unsigned int offset)
{
	unsigned int value;
	int ret = regmap_read(c->regmap, c->base + offset, &value);

	return ret ? ret : (int)value;
}

/* The receiver can assert PG before Q1 connects it to USBIN. Never treat
 * this preliminary route as ownership. No battery enable/PD/FC at this stage. */
int umi_rx_buck_route(struct smb5_chip *c)
{
	struct umi_rx_epp *s = c->epp;
	const char *stage = "pump-off";
	unsigned int typec;
	int pg, ret, typec_ret;

	if (!s || s->dirty) return 0;
	pg = smb5_wireless_rx_state(c);
	if (pg <= 0) return pg;
	ret = buck_pump_off(c);
	if (ret) goto report;
	s->preselect = true;
	stage = "save";
	ret = rx_begin(c, umi_rx1619_epoch(c->wireless_rx));
	if (ret) goto report;
	stage = "q1";
	ret = rx_field(c, ICL, 0, false);
	if (!ret) ret = rx_guard(c);
	if (!ret) ret = rx_pin(s->q1, true);
	if (ret) goto report;
	stage = "route-config";
	ret = rx_field(c, ADAPTER, 0, false);
	if (!ret) ret = rx_field(c, RANGE, 0x0c, false);
	if (!ret) ret = rx_field(c, OPTIONS, USBIN_MODE_CHG_BIT, false);
	if (!ret) ret = rx_field(c, OVERRIDE, ICL_OVERRIDE_BIT, false);
	if (!ret) ret = rx_field(c, LOAD, ICL_OVERRIDE_AFTER_APSD_BIT, false);
	if (ret) goto report;
	stage = "usbin-qualify";
	ret = buck_wait_usbin(c);
	if (ret) goto report;
	s->preselect = false;
	stage = "confirm-owner";
	ret = rx_guard(c);
	if (!ret && s->request) {
		stage = "apply-budget";
		ret = rx_budget(c, s->request);
	}
	if (!ret) return 0;

report:
	s->preselect = false;
	if (s->dirty) umi_rx_epp_latch(c);
	typec_ret = smb5_read_typec_misc(c, &typec);
	dev_warn_ratelimited(c->dev,
		"wireless RX preselect stage=%s rc=%d epoch=%d pg=%d q1=%d usb_rt=%d power_path=%d typec=%d\n",
		stage, ret, umi_rx1619_epoch(c->wireless_rx), smb5_wireless_rx_state(c),
		gpiod_get_value_cansleep(s->q1), buck_read_path(c, USBIN_INT_RT_STS_OFFSET),
		buck_read_path(c, POWER_PATH_STATUS), typec_ret ? typec_ret : (int)typec);
	return ret;
}

/* Without battery authentication the Umi DT caps FCC at 2 A. This is below
 * the six-pin worker's 2.5 A minimum taper vote; only its FV votes apply.
 * Do not count extra IRQ-driven polls as distinct taper samples. */
static int buck_float(struct umi_rx_epp *s, int uv, int soc, int ibat, int phase)
{
	static const int fv[] = {4240000, 4390000, 4450000};
	static const int fcc[] = {6000000, 4680000, 3740000};
	int idx = s->six_idx;

	if (idx < 0) {
		/* Starting at >=4.30 V has no six-pin vote in LOS. */
		idx = uv >= 4300000 ? 2 : uv < fv[0] - 20000 ? 0 : 1;
		s->six_idx = idx;
		s->next_taper = jiffies + msecs_to_jiffies(100);
	} else if (time_after_eq(jiffies, s->next_taper)) {
		bool taper = phase == TAPER_CHARGE;

		s->next_taper = jiffies + msecs_to_jiffies(taper ? 2000 : 10000);
		if (taper && idx < 2 && soc > 45 && ibat >= 0 && ibat <= fcc[idx + 1] + 50000) {
			if (++s->taper_count >= 2) { s->six_idx = ++idx; s->taper_count = 0; }
		} else {
			s->taper_count = 0;
		}
	}
	return min(fv[idx], 4400000); /* non-FFC Umi */
}

static int buck_limits(struct smb5_chip *c, int fv)
{
	struct umi_rx_epp *s = c->epp;
	const unsigned int hi = (u16)(-220 * 32767 / 10000), lo = 50 * 32767 / 10000;
	unsigned int wd, bite, aicl, eng, die_shutdown, value;
	int ret;

	/* Never raise the board's pre-session ceiling. */
	ret = rx_field(c, FV, min_t(unsigned int, s->saved[FV], (fv - 3600000) / 10000), false);
	if (!ret) ret = rx_field(c, TERM_MODE, 1, false);
	if (!ret) ret = rx_field(c, TERM_HI_M, hi >> 8, false);
	if (!ret) ret = rx_field(c, TERM_HI_L, hi & 0xff, false);
	if (!ret) ret = rx_field(c, TERM_LO_M, lo >> 8, false);
	if (!ret) ret = rx_field(c, TERM_LO_L, lo & 0xff, false);
	if (!ret) ret = regmap_read(c->regmap, c->base + 0xc0, &eng);
	if (!ret) ret = regmap_read(c->regmap, c->base + 0x670, &die_shutdown);
	if (!ret) ret = regmap_read(c->regmap, c->base + WD_CFG, &wd);
	if (!ret) ret = regmap_read(c->regmap, c->base + SNARL_BARK_BITE_WD_CFG, &bite);
	if (!ret) ret = regmap_read(c->regmap, c->base + USBIN_AICL_OPTIONS_CFG, &aicl);
	if (ret) return ret;
	if (!(die_shutdown & BIT(0)) || (eng & BIT(3)) || !(wd & WDOG_TIMER_EN_BIT) || !(bite & BITE_WDOG_DISABLE_CHARGING_CFG_BIT) ||
	    !(aicl & USBIN_AICL_EN_BIT)) return -EPERM;
	ret = regmap_read(c->regmap, c->base + USBIN_CURRENT_LIMIT_CFG, &value);
	if (!ret && (!value || value > 600000 / CURRENT_SCALE_FACTOR)) return -EPERM;
	if (!ret) ret = regmap_read(c->regmap, c->base + FAST_CHARGE_CURRENT_CFG, &value);
	return ret ?: (!value || value > 2000000 / CURRENT_SCALE_FACTOR ? -EPERM : 0);
}

static int buck_output_guard(struct smb5_chip *c)
{
	unsigned int mode;
	int ret = regmap_read(c->epp->divider, 0x0f, &mode);

	if (ret) return ret;
	if ((mode & 3) != 2 || gpiod_get_value_cansleep(c->epp->q1) != 1) return -ENOLINK;
	return rx_guard(c);
}

int umi_rx_buck_tick(struct smb5_chip *c)
{
	struct umi_rx_epp *s = c->epp;
	unsigned int phase, fault;
	int temp, soc, uv, ua, vout, iout, health, present, state, ret;

	if (!s || !s->dirty || !s->calibrated || !s->identified || s->mode != 2)
		return c->rx_buck_active ? -ENOLINK : 0;
	/* RAM acceptance only: never leave the test charging unattended. */
	if (c->rx_buck_active && time_after_eq(jiffies, s->deadline)) return -ETIME;
	ret = rx_guard(c);
	if (!ret) ret = buck_pump_off(c);
	if (!ret) ret = buck_value(c->bms, POWER_SUPPLY_PROP_PRESENT, &present);
	if (!ret) ret = buck_value(c->bms, POWER_SUPPLY_PROP_TEMP, &temp);
	if (!ret) ret = buck_value(c->bms, POWER_SUPPLY_PROP_CAPACITY, &soc);
	if (!ret) ret = buck_value(c->bms, POWER_SUPPLY_PROP_CURRENT_NOW, &ua);
	if (!ret) ret = buck_value(c->bms, POWER_SUPPLY_PROP_VOLTAGE_NOW, &uv);
	if (!ret) ret = buck_value(c->wireless_rx, POWER_SUPPLY_PROP_VOLTAGE_NOW, &vout);
	if (!ret) ret = buck_value(c->wireless_rx, POWER_SUPPLY_PROP_CURRENT_NOW, &iout);
	if (!ret) ret = smb5_get_prop_health(c, &health);
	if (!ret) ret = regmap_read(c->regmap, c->base + BATTERY_CHARGER_STATUS_1, &phase);
	if (!ret) ret = regmap_read(c->regmap, c->base + BATTERY_CHARGER_STATUS_2, &fault);
	if (ret) return ret;
	phase &= BATTERY_CHARGER_STATUS_MASK;
	if (soc >= UMI_CHARGE_END_SOC || phase == TERMINATE_CHARGE) c->full_bypass = true;
	else if (soc >= 0 && soc <= UMI_CHARGE_RESUME_SOC) c->full_bypass = false;
	if (present != 1 || health != POWER_SUPPLY_HEALTH_GOOD || temp <= 150 || temp >= 450 ||
	    uv <= 0 || uv > 4400000 || ua > 2000000 || soc < 0 || soc > 100 || c->full_bypass ||
	    (fault & GENMASK(2, 0)) || vout <= 0 || vout > 11000000 || iout < 0 || iout > 1500000)
		return -EPERM;
	ret = buck_limits(c, buck_float(s, uv, soc, ua, phase));
	if (!ret) ret = buck_output_guard(c);
	if (!ret && !c->rx_buck_active) {
		ret = regmap_update_bits(c->regmap, c->base + CHARGING_ENABLE_CMD,
					 CHARGING_ENABLE_CMD_BIT, CHARGING_ENABLE_CMD_BIT);
		if (!ret) ret = smb5_get_prop_charging_enabled(c, &state);
		if (!ret && state != POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO) ret = -EIO;
		if (!ret) {
			s->deadline = jiffies + msecs_to_jiffies(60000);
			WRITE_ONCE(c->rx_buck_active, true);
		}
	}
	if (!ret) ret = buck_output_guard(c);
	if (!ret) ret = regmap_write(c->regmap, c->base + BARK_BITE_WDOG_PET, BARK_BITE_WDOG_PET_BIT);
	if (!ret) dev_info(c->dev, "umi-rx-buck epoch=%d bq_off=1 soc=%d temp_decic=%d vbat_uv=%d ibat_ua=%d rx_uv=%d rx_ua=%d phase=%u\n",
			   s->epoch, soc, temp, uv, ua, vout, iout, phase);
	return ret;
}
