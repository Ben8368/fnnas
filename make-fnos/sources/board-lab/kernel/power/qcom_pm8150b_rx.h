/* SPDX-License-Identifier: GPL-2.0-only */
/* Built-in Umi board glue; no exported symbols or userspace control ABI. */
#ifndef QCOM_PM8150B_RX_H
#define QCOM_PM8150B_RX_H
struct power_supply;
struct smb5_chip;
int smb5_rx_attach(struct smb5_chip *chip);
int smb5_rx_subscribe(struct smb5_chip *chip);
#ifdef CONFIG_UMI_RX_EPP
struct device;
struct regmap;
int umi_ln_forward(struct regmap *map, int (*guard)(void *), void *ctx);
int umi_rx_epp_attach(struct smb5_chip *chip);
int umi_rx_epp_event(void *ctx, unsigned int cmd, unsigned int value, int epoch);
int umi_rx_epp_poll(struct smb5_chip *chip);
int umi_rx_epp_release(struct smb5_chip *chip);
bool umi_rx_epp_fault(struct smb5_chip *chip);
void umi_rx_epp_latch(struct smb5_chip *chip);
bool umi_rx_epp_owned(struct smb5_chip *chip);
/* Identify the loaded FG profile, not pack authentication. Negative errno on failure. */
int umi_fg_loaded_profile(struct power_supply *psy, int *ffc_term_ma);
int umi_rx1619_epoch(struct power_supply *psy);
#endif
#ifdef CONFIG_UMI_RX_BUCK
int umi_rx_buck_charge_state(struct smb5_chip *chip);
int umi_rx_buck_tick(struct smb5_chip *chip);
int umi_rx_buck_route(struct smb5_chip *chip);
int umi_rx1619_preselect_tx_id(struct power_supply *psy, int epoch,
			       int (*guard)(void *, bool), void *ctx);
int umi_rx1619_preselect_service(struct power_supply *psy,
				int (*check_input)(void *, bool), void *ctx);
#endif
#ifdef CONFIG_UMI_RX_LINK
int smb5_rx_cable(struct smb5_chip *chip);
int umi_rx1619_pin(struct power_supply *psy, bool enable);
int umi_rx1619_pin_status(struct power_supply *psy);
int smb5_rx_sync_pin(struct smb5_chip *chip);
/* The sole consumer serializes calls under its charger lock. NULL revokes. */
int umi_rx1619_service(struct power_supply *psy, int (*check_input)(void *, bool), void *ctx);
void smb5_rx_link_step(struct smb5_chip *chip, bool eligible);
#endif
#endif
