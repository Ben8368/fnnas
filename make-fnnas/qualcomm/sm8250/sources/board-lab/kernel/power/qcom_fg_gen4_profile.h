/* SPDX-License-Identifier: GPL-2.0-only */
/* Gen4 DMA arbitration adapted from fg-memif.c and qpnp-fg-gen4.c.
 * Copyright (c) 2016-2018, 2021, The Linux Foundation. All rights reserved.
 * Umi profile comparison: LineageOS 71b13e62, see NOTICE.md.
 */
#include <linux/delay.h>
#include <soc/qcom/qcom-spmi-pmic.h>
#include "qcom_pm8150b_rx.h"

/* PM8150B v2, two bytes per word, partition windows start at offset 0x20. */
#define FG_PROFILE_PREFIX  (0x4520 + (65 - 64) * 2)
#define FG_PROFILE_FLAGS   (0x4720 + (299 - 275) * 2)
#define FG_MEM_ARB         0x4340
#define FG_MEM_CFG         0x4350
#define FG_MEM_STS         0x4310
#define FG_DMA_STS         0x4370
#define FG_ACCESS          (BIT(7) | BIT(5))

static int fg_match_loaded(unsigned int flags, const u8 *prefix, int *term_ma)
{
	static const struct { u8 bytes[24]; int ma; } profiles[] = {
		{{0x09,0x00,0x7a,0xe3,0xc6,0xdd,0x23,0xe2,0x90,0xdd,0x00,0x00,
		  0x41,0xb5,0xfb,0x81,0x00,0x00,0x27,0x8d,0x4d,0x8d,0x30,0x80}, -941},
		{{0x09,0x00,0x8a,0xe3,0xcf,0xd4,0x19,0x00,0x7b,0xd4,0x00,0x00,
		  0x07,0xb5,0xed,0x82,0xfc,0x87,0xf3,0xa5,0x6a,0x92,0x56,0x80}, -1035},
	};
	unsigned int i;

	/* PROFILE_LOAD plus exactly one of the seven LOS integrity states. */
	switch (flags) {
	case 0x09: case 0x03: case 0x07: case 0x0d:
	case 0x13: case 0x17: case 0x1d:
		break;
	default:
		return -ENODATA;
	}
	for (i = 0; i < ARRAY_SIZE(profiles); i++) {
		if (!memcmp(prefix, profiles[i].bytes, sizeof(profiles[i].bytes))) {
			*term_ma = profiles[i].ma;
			return 0;
		}
	}
	return -ENODATA;
}

static int fg_idle_field(struct regmap *map, unsigned int reg, unsigned int bits)
{
	unsigned int v;
	int ret = regmap_read(map, reg, &v);

	return ret ?: (v & bits ? -EBUSY : 0);
}

static int fg_release_field(struct regmap *map, unsigned int reg, unsigned int bits)
{
	int ret = regmap_update_bits(map, reg, bits, 0);

	return ret ?: fg_idle_field(map, reg, bits);
}

/* Single consumer under SMB5 mutex. No SRAM writes, no profile load/restart,
 * no fault clearing. Hold one grant for integrity and prefix together. */
static int fg_read_loaded(struct regmap *map, int *term_ma, bool *release_failed)
{
	unsigned int flags, grant;
	u8 prefix[24];
	int i, ret, cfg_ret, arb_ret;

	ret = fg_idle_field(map, FG_MEM_ARB, BIT(0));
	if (!ret) ret = fg_idle_field(map, FG_MEM_CFG, FG_ACCESS);
	if (!ret) ret = fg_idle_field(map, FG_DMA_STS, BIT(1) | BIT(2));
	if (ret) return ret;
	ret = regmap_update_bits(map, FG_MEM_ARB, BIT(0), BIT(0));
	if (!ret) ret = regmap_update_bits(map, FG_MEM_CFG, FG_ACCESS, BIT(7));
	if (!ret) {
		usleep_range(40, 41);
		ret = regmap_read_poll_timeout(map, FG_MEM_STS, grant, grant & BIT(3),
					       10000, 500000);
	}
	if (!ret) ret = regmap_read(map, FG_PROFILE_FLAGS, &flags);
	if (!ret) ret = regmap_bulk_read(map, FG_PROFILE_PREFIX, prefix, sizeof(prefix));
	if (!ret) ret = fg_idle_field(map, FG_DMA_STS, BIT(1) | BIT(2));
	/* Both releases even after an ambiguous request write or read error. */
	for (i = 0; i < 3; i++) {
		cfg_ret = fg_release_field(map, FG_MEM_CFG, FG_ACCESS);
		arb_ret = fg_release_field(map, FG_MEM_ARB, BIT(0));
		if (!cfg_ret && !arb_ret) break;
		ret = cfg_ret ?: arb_ret; /* reject this sample even if retry succeeds */
	}
	if (cfg_ret || arb_ret) WRITE_ONCE(*release_failed, true);
	return cfg_ret ?: arb_ret ?: ret ?: fg_match_loaded(flags, prefix, term_ma);
}

int umi_fg_loaded_profile(struct power_supply *psy, int *ffc_term_ma)
{
	const struct qcom_spmi_pmic *rev;
	struct qcom_fg_chip *chip;

	if (!psy || psy->desc != &batt_psy_desc || !ffc_term_ma) return -EINVAL;
	chip = power_supply_get_drvdata(psy);
	if (!READ_ONCE(chip->initialized)) return -EAGAIN;
	if (chip->ops != &ops_fg_gen4 || chip->base != 0x4000) return -ENODEV;
	rev = qcom_pmic_get(chip->dev);
	if (IS_ERR(rev)) return PTR_ERR(rev);
	/* V1 requires the ALG_ACTIVE workaround. Never request DMA there. */
	if (rev->subtype != PM8150B_SUBTYPE || rev->major != 2) return -ENODEV;
	if (READ_ONCE(chip->dma_release_failed)) return -EIO;
	return fg_read_loaded(chip->regmap, ffc_term_ma, &chip->dma_release_failed);
}
