// SPDX-License-Identifier: GPL-2.0-only
/* Register definitions from the LN8282 downstream driver.
 * Copyright (C) 2019 Lion Semiconductor Inc.
 * Copyright (C) 2020 XiaoMi, Inc.
 * Original author: Jae Lee <kjaelee@lionsemi.com>
 */

#include <linux/bits.h>
#include <linux/devm-helpers.h>
#include <linux/i2c.h>
#include <linux/jiffies.h>
#include <linux/module.h>
#include <linux/power_supply.h>
#include <linux/workqueue.h>

#define LN8282_REG_DEVICE_0_STS	0x09
#define LN8282_REG_HV_SC_CTRL_0	0x0f
#define LN8282_REG_FAULT_CTRL	0x14
#define LN8282_REG_STS_F		0x42
#define LN8282_REG_STS_G		0x43
#define LN8282_VIN_SWITCH_OK	BIT(3)
#define LN8282_MODE_MASK	GENMASK(1, 0)
#define LN8282_SAMPLE_INTERVAL_MS 2000

struct ln8282_observer {
	struct i2c_client *client;
	struct power_supply *rx;
	struct delayed_work sample;
};

struct ln8282_snapshot {
	u8 device_status, ctrl, fault_ctrl, status_f, status_g;
};

/* Return 1 only for a full register sample bracketed by RX power-good. */
static int ln8282_read_snapshot(struct ln8282_observer *observer,
				struct ln8282_snapshot *snapshot)
{
	struct i2c_client *client = observer->client;
	union power_supply_propval online;
	int ret, device_status, ctrl, fault_ctrl, status_f, status_g;

	ret = power_supply_get_property(observer->rx, POWER_SUPPLY_PROP_ONLINE, &online);
	if (ret || online.intval != 1)
		return ret;
	device_status = i2c_smbus_read_byte_data(client, LN8282_REG_DEVICE_0_STS);
	if (device_status < 0)
		return device_status;
	ctrl = i2c_smbus_read_byte_data(client, LN8282_REG_HV_SC_CTRL_0);
	if (ctrl < 0)
		return ctrl;
	fault_ctrl = i2c_smbus_read_byte_data(client, LN8282_REG_FAULT_CTRL);
	if (fault_ctrl < 0)
		return fault_ctrl;
	status_f = i2c_smbus_read_byte_data(client, LN8282_REG_STS_F);
	if (status_f < 0)
		return status_f;
	status_g = i2c_smbus_read_byte_data(client, LN8282_REG_STS_G);
	if (status_g < 0)
		return status_g;
	ret = power_supply_get_property(observer->rx, POWER_SUPPLY_PROP_ONLINE, &online);
	if (ret || online.intval != 1)
		return ret;

	*snapshot = (struct ln8282_snapshot) {
		.device_status = device_status,
		.ctrl = ctrl,
		.fault_ctrl = fault_ctrl,
		.status_f = status_f,
		.status_g = status_g,
	};
	return 1;
}

static void ln8282_sample(struct work_struct *work)
{
	struct ln8282_observer *observer = container_of(to_delayed_work(work),
							struct ln8282_observer, sample);
	struct ln8282_snapshot snapshot;
	struct device *dev = &observer->client->dev;
	int ret = ln8282_read_snapshot(observer, &snapshot);

	if (ret > 0)
		dev_info(dev, "ln8282 observe mode_cfg=%u ctrl=0x%02x sts_f=0x%02x sts_g=0x%02x device_sts=0x%02x vin_switch_ok=%d fault_ctrl=0x%02x\n",
			 (unsigned int)(snapshot.ctrl & LN8282_MODE_MASK), snapshot.ctrl,
			 snapshot.status_f, snapshot.status_g, snapshot.device_status,
			 !!(snapshot.device_status & LN8282_VIN_SWITCH_OK), snapshot.fault_ctrl);
	else if (ret < 0)
		dev_err_ratelimited(dev, "ln8282 observe read failed: %d\n", ret);

	schedule_delayed_work(&observer->sample, msecs_to_jiffies(LN8282_SAMPLE_INTERVAL_MS));
}

static int ln8282_observe_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct ln8282_observer *observer;
	int ret;

	if (IS_ENABLED(CONFIG_UMI_RX_NFC_COEX) || IS_ENABLED(CONFIG_UMI_RX_ENABLE_EXPERIMENT))
		return -ENODEV;
	if (!i2c_check_functionality(client->adapter, I2C_FUNC_SMBUS_READ_BYTE_DATA))
		return -EOPNOTSUPP;
	observer = devm_kzalloc(dev, sizeof(*observer), GFP_KERNEL);
	if (!observer)
		return -ENOMEM;
	observer->client = client;
	observer->rx = devm_power_supply_get_by_reference(dev, "power-supplies");
	if (IS_ERR(observer->rx))
		return dev_err_probe(dev, PTR_ERR(observer->rx), "RX supply lookup\n");
	if (!observer->rx)
		return -EPROBE_DEFER;
	if (!device_link_add(dev, observer->rx->dev.parent, DL_FLAG_AUTOREMOVE_CONSUMER))
		return -ENOMEM;
	ret = devm_delayed_work_autocancel(dev, &observer->sample, ln8282_sample);
	if (ret)
		return ret;
	schedule_delayed_work(&observer->sample, msecs_to_jiffies(LN8282_SAMPLE_INTERVAL_MS));
	dev_info(dev, "ln8282 observe ready\n");
	return 0;
}

static const struct of_device_id ln8282_observe_match[] = {
	{ .compatible = "xiaomi,umi-ln8282" },
	{ }
};
MODULE_DEVICE_TABLE(of, ln8282_observe_match);

static struct i2c_driver ln8282_observe_driver = {
	.driver = {
		.name = "ln8282-observe",
		.of_match_table = ln8282_observe_match,
	},
	.probe = ln8282_observe_probe,
};
module_i2c_driver(ln8282_observe_driver);

MODULE_DESCRIPTION("Umi LN8282 read-only wireless RX diagnostics");
MODULE_LICENSE("GPL");
