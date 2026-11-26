// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (c) 2024, Teguh Sobirin <teguh@sobir.in>.
 *
 * This driver is for the switch-mode battery charger power delivery
 * and boost hardware found in pm8150b and related PMICs.
 * This work based on pmi8998 charger driver by
 * Caleb Connolly <caleb.connolly@linaro.org>
 * Should be merged with the existing charger driver in the future.
 */

#include "qcom_pm8150b_internal.h"

int smb5_get_prop_charging_enabled(struct smb5_chip *chip, int *val)
{
	unsigned int charging_enabled;
	int rc = regmap_read(chip->regmap, chip->base + CHARGING_ENABLE_CMD, &charging_enabled);
	if (rc < 0) {
		dev_err(chip->dev, "Failed to read charging enabled status, rc = %d", rc);
		return rc;
	}
	*val = charging_enabled & CHARGING_ENABLE_CMD_BIT ?
		POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO :
		POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE;
	return 0;
}

int smb5_get_current_limit(struct smb5_chip *chip,
					 unsigned int *val)
{
	int rc = regmap_read(chip->regmap, chip->base + USBIN_CURRENT_LIMIT_CFG, val);

	if (rc >= 0)
		*val *= CURRENT_SCALE_FACTOR;
	return rc;
}

int smb5_set_current_limit(struct smb5_chip *chip, unsigned int val)
{
	unsigned int val_raw, actual;
	int ret;

	if (val > UMI_CHARGE_USB_ICL_UA) {
		dev_err(chip->dev,
			"LOS Umi USB input current limit exceeded");
		return -EINVAL;
	}
	val_raw = val / CURRENT_SCALE_FACTOR;

	ret = regmap_write(chip->regmap, chip->base + USBIN_CURRENT_LIMIT_CFG, val_raw);
	if (ret)
		return ret;
	/* Verify the configured ceiling, not the effective AICL or load current. */
	ret = regmap_read(chip->regmap, chip->base + USBIN_CURRENT_LIMIT_CFG, &actual);
	return ret ? ret : actual == val_raw ? 0 : -EIO;
}

int smb5_set_prop_charging_enabled(struct smb5_chip *chip, unsigned int val)
{
	int rc, online, state;

	if (val != POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO &&
	    val != POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE)
		return -EINVAL;
	if (val == POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO) {
		if (IS_ENABLED(CONFIG_UMI_RX_DIAGNOSTIC))
			return -EPERM;
		if (chip->stop_pending)
			return -EBUSY;
		/* Only the wired SMB5 policy may enable this shared charger. */
		rc = smb5_get_prop_usb_online(chip, &online);
		if (rc || !online)
			return rc ? rc : -ENOLINK;
	}

	rc = regmap_update_bits(chip->regmap, chip->base + CHARGING_ENABLE_CMD,
				CHARGING_ENABLE_CMD_BIT,
				val == POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO ?
				CHARGING_ENABLE_CMD_BIT : 0);
	if (rc || val == POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE)
		return rc;
	rc = smb5_get_prop_charging_enabled(chip, &state);
	if (rc)
		return rc;
	return state == POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO ? 0 : -EIO;
}

int smb5_inhibit_with_fallback(struct smb5_chip *chip, const char *where)
{
	unsigned int input;
	int rc, suspend_rc, state;

	rc = smb5_set_prop_charging_enabled(chip,
			POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE);
	if (!rc) {
		rc = smb5_get_prop_charging_enabled(chip, &state);
		if (!rc && state != POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE)
			rc = -EBUSY;
	}
	/* USBIN suspend is a fallback. Only the charger command confirms stop. */
	chip->stop_pending = !!rc;
	if (rc) {
		suspend_rc = regmap_update_bits(chip->regmap,
			chip->base + USBIN_CMD_IL, USBIN_SUSPEND_BIT,
			USBIN_SUSPEND_BIT);
		if (!suspend_rc) {
			suspend_rc = regmap_read(chip->regmap, chip->base + USBIN_CMD_IL, &input);
			if (!suspend_rc && !(input & USBIN_SUSPEND_BIT))
				suspend_rc = -EIO;
		}
		dev_err(chip->dev,
			"miseed-charge %s stop failed rc=%d input_suspend_rc=%d; watchdog not fed\n",
			where, rc, suspend_rc);
	}

	return rc;
}
