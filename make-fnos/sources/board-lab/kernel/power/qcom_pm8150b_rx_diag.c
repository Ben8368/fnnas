// SPDX-License-Identifier: GPL-2.0-only
/* Umi shared-input arbitration, optional RX diagnostics and receiver link. */
#include "qcom_pm8150b_internal.h"
#include "qcom_pm8150b_rx.h"

#define SMB5_RX_REFERENCE "qcom,wireless-rx"

static int smb5_rx_changed(struct notifier_block *notifier,
			   unsigned long event, void *data)
{
	struct smb5_chip *chip = container_of(notifier, struct smb5_chip, rx_notifier);

	if (event != PSY_EVENT_PROP_CHANGED || (data != chip->wireless_rx &&
	    !(IS_ENABLED(CONFIG_UMI_RX_LINK) && data == chip->pd)))
		return NOTIFY_DONE;
	mutex_lock(&chip->lock);
	if (!chip->stopping)
		mod_delayed_work(system_wq, &chip->status_change_work, 0);
	mutex_unlock(&chip->lock);
	return NOTIFY_OK;
}

static void smb5_rx_unregister(void *data)
{
	struct smb5_chip *chip = data;

	power_supply_unreg_notifier(&chip->rx_notifier);
}

int smb5_rx_attach(struct smb5_chip *chip)
{
	struct device *dev = chip->dev;

	if (!device_property_present(dev, SMB5_RX_REFERENCE))
		return 0;
	chip->wireless_rx = devm_power_supply_get_by_reference(dev, SMB5_RX_REFERENCE);
	if (IS_ERR(chip->wireless_rx))
		return PTR_ERR(chip->wireless_rx);
	if (!chip->wireless_rx)
		return -EPROBE_DEFER;
	if (!device_link_add(dev, chip->wireless_rx->dev.parent, DL_FLAG_AUTOREMOVE_CONSUMER))
		return -ENOMEM;
#ifdef CONFIG_UMI_RX_EPP
	return umi_rx_epp_attach(chip);
#else
	return 0;
#endif
}

int smb5_rx_subscribe(struct smb5_chip *chip)
{
	int ret;

	if (!chip->wireless_rx)
		return 0;
	chip->rx_notifier.notifier_call = smb5_rx_changed;
	ret = power_supply_reg_notifier(&chip->rx_notifier);
	if (ret)
		return ret;
	return devm_add_action_or_reset(chip->dev, smb5_rx_unregister, chip);
}

int smb5_rx_diag_check_off(struct smb5_chip *chip)
{
	int state, ret;

	ret = smb5_get_prop_charging_enabled(chip, &state);
	if (ret)
		return ret;
	return state == POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE ? 0 : -EBUSY;
}

/* Called with the charger lock. An unexpected enable is recorded even when
 * the subsequent stop succeeds, so the diagnostic session cannot pass.
 */
void smb5_rx_diag_sample(struct smb5_chip *chip)
{
	unsigned int cc;
	int charge_ret = smb5_rx_diag_check_off(chip);
	int cc_ret = smb5_read_typec_misc(chip, &cc);

	if (charge_ret || chip->stop_pending) {
		int stop_ret = smb5_inhibit_with_fallback(chip, "rx-diagnostic");

		if (charge_ret || stop_ret)
			dev_err_ratelimited(chip->dev,
					    "umi-rx-diag smb5 readback failed rc=%d stop_rc=%d\n",
					    charge_ret, stop_ret);
		charge_ret = charge_ret ?: stop_ret;
	}
	if (cc_ret)
		dev_info(chip->dev, "umi-rx-diag smb5_off=%u cc_error=%d\n",
			 !charge_ret, cc_ret);
	else
		dev_info(chip->dev, "umi-rx-diag smb5_off=%u cc_attached=%u vbus_present=%u cc_status=0x%02x\n",
			 !charge_ret, !!(cc & TYPEC_CC_ATTACHED), !!(cc & TYPEC_VBUS_DETECT), cc);
}

#ifdef CONFIG_UMI_RX_LINK
/* Umi is sink-only. CC attachment alone must suppress RX even while TCPM
 * is negotiating. Shared VBUS alone is not a cable (it may come from RX).
 */
int smb5_rx_cable(struct smb5_chip *chip)
{
	union power_supply_propval sink;
	unsigned int cc;
	int ret = smb5_read_typec_misc(chip, &cc);

	if (ret || (cc & TYPEC_CC_ATTACHED))
		return ret ?: 1;
	ret = power_supply_get_property(chip->pd, POWER_SUPPLY_PROP_ONLINE, &sink);
	return ret ?: !!sink.intval;
}

int smb5_rx_sync_pin(struct smb5_chip *chip)
{
	int cable, ret;

	if (!chip->wireless_rx)
		return 0;
	cable = smb5_rx_cable(chip);
#ifdef CONFIG_UMI_RX_EPP
	if (umi_rx_epp_fault(chip))
		return umi_rx1619_pin(chip->wireless_rx, false);
#endif
	if (!cable && !chip->stopping && !chip->stop_pending && !chip->pps_owned &&
	    !chip->pps_fault && !chip->pd_transition && !chip->inhibit) {
#ifdef CONFIG_UMI_RX_BUCK
		ret = umi_rx_buck_charge_state(chip);
#else
		ret = smb5_rx_diag_check_off(chip);
#endif
		if (!ret) {
			ret = umi_rx1619_pin(chip->wireless_rx, true);
			if (!ret && !(cable = smb5_rx_cable(chip))) {
#ifdef CONFIG_UMI_RX_BUCK
				return umi_rx_buck_route(chip);
#else
				return 0;
#endif
			}
		}
		if (ret)
			cable = ret;
	}
	ret = umi_rx1619_pin(chip->wireless_rx, false);
	return ret ?: (cable < 0 ? cable : 0);
}

/* Re-evaluate physical source and battery inhibit before each mailbox write.
 * No TCPM/PPS operation, wireless pump request or charge-enable permission.
 */
static int smb5_rx_link_guard(void *ctx, bool limit_bpp)
{
	struct smb5_chip *chip = ctx;
	unsigned int ua;
	int ret, owner;

	if (chip->stopping || chip->stop_pending || chip->pps_owned || chip->pps_fault ||
	    chip->pd_transition || chip->inhibit || chip->cooling_state)
		return -EBUSY;
#ifdef CONFIG_UMI_RX_BUCK
	ret = umi_rx_buck_charge_state(chip);
#else
	ret = smb5_rx_diag_check_off(chip);
#endif
	if (ret)
		return ret;
	owner = smb5_usbin_owner(chip);
	if (owner != SMB5_INPUT_RX)
		return owner < 0 ? owner : -ENOLINK;
#ifdef CONFIG_UMI_RX_EPP
	/* The EPP profile owns a reversible BPP/EPP current budget. */
	return 0;
#endif
	if (!limit_bpp)
		return 0;
	/* LOS DC_LOW_CURRENT on BPP LDO-on. Never raise an existing ceiling.
	 * Keep the pre-RX user ceiling for the normal wired recovery ramp.
	 */
	ret = smb5_get_current_limit(chip, &ua);
	if (ret || ua <= 200000)
		return ret;
	owner = smb5_usbin_owner(chip);
	if (owner != SMB5_INPUT_RX)
		return owner < 0 ? owner : -ENOLINK;
	ret = smb5_set_current_limit(chip, 200000);
	if (!ret) {
		if (!chip->policy_icl_valid || ua != chip->policy_icl_ua)
			chip->saved_icl_ua = ua;
		chip->policy_icl_ua = 200000;
		chip->policy_icl_valid = true;
	}
	return ret;
}

void smb5_rx_link_step(struct smb5_chip *chip, bool eligible)
{
	int ret;

	if (!chip->wireless_rx)
		return;
	ret = umi_rx1619_service(chip->wireless_rx, eligible ? smb5_rx_link_guard : NULL, chip);
#ifdef CONFIG_UMI_RX_EPP
	if (eligible && !ret)
		ret = umi_rx_epp_poll(chip);
#ifdef CONFIG_UMI_RX_BUCK
	if (eligible && !ret) ret = umi_rx_buck_tick(chip);
#endif
	if (ret || !eligible) {
		int cleanup;

		if (ret && (ret != -EAGAIN || umi_rx_epp_owned(chip))) umi_rx_epp_latch(chip);
		umi_rx1619_service(chip->wireless_rx, NULL, chip);
		cleanup = umi_rx_epp_release(chip);
		if (cleanup) {
			umi_rx_epp_latch(chip);
			dev_err_ratelimited(chip->dev, "RX limits not restored: %d\n", cleanup);
		}
	}
#endif
	if (ret)
		dev_warn_ratelimited(chip->dev, "wireless RX link stopped: %d\n", ret);
}
#endif
