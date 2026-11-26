// SPDX-License-Identifier: GPL-2.0-only
/* Forward Bx sequence from LineageOS 71b13e62, ln8282.c.
 * Copyright (C) 2019 Lion Semiconductor Inc.; Copyright (C) 2020 XiaoMi, Inc.
 * Original author: Jae Lee <kjaelee@lionsemi.com>
 */
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/regmap.h>
#include "qcom_pm8150b_rx.h"

/* The SMB5 arbiter owns the transaction, not a writable userspace mode.
 * Return the actual forward mode (1 bypass, 2 switching), never infer it
 * from a write succeeding. Reject standby, alternate mode and I/O errors.
 */
int umi_ln_forward(struct regmap *map, int (*check_session)(void *), void *ctx)
{
	static const struct { unsigned int reg, mask, val; } seq[] = {
		{0x10, 0x60, 0x40}, {0x15, 0x10, 0}, {0x0e, 0x40, 0x40},
		{0x14, 0xff, 0x04}, {0x0f, 3, 2},
	};
	unsigned int vin, mode;
	int ret, lock, i;

	ret = check_session(ctx);
	if (!ret)
		ret = regmap_read(map, 0x09, &vin);
	if (ret)
		return ret;
	if (vin & BIT(3)) {
		ret = check_session(ctx);
		if (ret)
			return ret;
		ret = regmap_write(map, 0x20, 0x5b);
		if (!ret)
			ret = check_session(ctx);
		if (!ret)
			ret = regmap_update_bits(map, 0x25, BIT(2), BIT(2));
		/* An I2C error does not prove the unlock was not received. */
		lock = regmap_write(map, 0x20, 0);
		if (lock || ret)
			return lock ?: ret;
		for (i = 0; i < ARRAY_SIZE(seq); i++) {
			ret = check_session(ctx);
			if (!ret)
				ret = regmap_update_bits(map, seq[i].reg, seq[i].mask, seq[i].val);
			if (ret)
				return ret;
		}
		/* Keep the VIN check enabled after the forward transition. */
		msleep(100);
	}
	msleep(10);
	ret = check_session(ctx);
	if (!ret)
		ret = regmap_read(map, 0x0f, &mode);
	if (ret)
		return ret;
	mode &= 3;
	if (mode == 1 || (mode == 2 && (vin & BIT(3))))
		return mode;
	return -ENOLINK;
}

static int ln_forward_probe(struct i2c_client *client)
{
	static const struct regmap_config config = { .reg_bits = 8, .val_bits = 8 };
	struct regmap *map = devm_regmap_init_i2c(client, &config);

	return PTR_ERR_OR_ZERO(map);
}

static const struct of_device_id ln_forward_match[] = {
	{ .compatible = "xiaomi,umi-ln8282" }, { }
};
MODULE_DEVICE_TABLE(of, ln_forward_match);
static struct i2c_driver ln_forward_driver = {
	.driver = { .name = "umi-ln8282-forward", .of_match_table = ln_forward_match },
	.probe = ln_forward_probe,
};
module_i2c_driver(ln_forward_driver);
MODULE_LICENSE("GPL");
