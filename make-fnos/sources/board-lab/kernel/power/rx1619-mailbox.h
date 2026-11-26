/* SPDX-License-Identifier: GPL-2.0-only */
/* RX mailbox fields from colin's NuVolta driver, LineageOS 71b13e62. */
#ifndef MISEED_RX1619_MAILBOX_H
#define MISEED_RX1619_MAILBOX_H

#define RX1619_MAILBOX_CMD	0x20
#define RX1619_MAILBOX_FLAGS	0x21
#define RX1619_MAILBOX_HW_H	0x22
#define RX1619_MAILBOX_HW_L	0x23
#define RX1619_MAILBOX_FW	0x24
#define RX1619_LDO_ON		0x01
#define RX1619_MAILBOX_CMD_10	0x10
#define RX1619_MAILBOX_CMD_UNKNOWN	0x100
#define RX1619_MAILBOX_TRACE_MAX	32

/* RX messages share four payload registers. */
struct rx1619_frame {
	unsigned int cmd, data[4];
};

static int rx1619_read_frame(struct regmap *map, struct rx1619_frame *out,
			     unsigned int *observed_cmd)
{
	struct rx1619_frame frame;
	int i, ret;

	ret = regmap_read(map, RX1619_MAILBOX_CMD, &frame.cmd);
	if (ret)
		return ret;
	*observed_cmd = frame.cmd;
	if (frame.cmd != RX1619_LDO_ON && frame.cmd != RX1619_MAILBOX_CMD_10
#ifdef CONFIG_UMI_RX_LINK
	    && !(frame.cmd >= 2 && frame.cmd <= 6) && frame.cmd != 0x0d
#endif
	   )
		return -ENODATA;
	for (i = 0; i < 4; i++) {
		ret = regmap_read(map, RX1619_MAILBOX_FLAGS + i, &frame.data[i]);
		if (ret)
			return ret;
	}
	*out = frame;
	return 0;
}

static int rx1619_snapshot_frame(struct regmap *map, struct gpio_desc *pg,
				 atomic_t *pg_irqs, int epoch, struct rx1619_frame *out,
				 unsigned int *observed_cmd, int *pg_before, int *pg_after)
{
	struct rx1619_frame first, second;
	int i, ret;

	ret = gpiod_get_value_cansleep(pg);
	*pg_before = ret;
	if (ret <= 0)
		return ret ? ret : -ENODATA;
	ret = rx1619_read_frame(map, &first, observed_cmd);
	if (ret)
		return ret;
	ret = rx1619_read_frame(map, &second, observed_cmd);
	if (ret)
		return ret;
	ret = gpiod_get_value_cansleep(pg);
	*pg_after = ret;
	if (ret <= 0)
		return ret ? ret : -ENODATA;
	if (epoch != atomic_read(pg_irqs) || first.cmd != second.cmd)
		return -EAGAIN;
	for (i = 0; i < 4; i++)
		if (first.data[i] != second.data[i])
			return -EAGAIN;
	if (second.cmd == RX1619_LDO_ON && (second.data[1] != 0x16 || second.data[2] != 0x19))
		return -ENODEV;
	*out = second;
	return 0;
}

static irqreturn_t rx1619_mailbox_changed(int irq, void *data)
{
	struct rx1619 *rx = data;
	struct rx1619_frame frame;
	unsigned int command = RX1619_MAILBOX_CMD_UNKNOWN;
	int pg_before = -EINPROGRESS, pg_after = -EINPROGRESS;
	int count = atomic_inc_return(&rx->mailbox_irqs);
	int epoch = atomic_read(&rx->pg_irqs);
	int ret;

	/* Stop observing after a bounded read-only trace; never acknowledge blindly. */
	if (count >= RX1619_MAILBOX_TRACE_MAX) {
		disable_irq_nosync(irq);
		dev_info(rx->dev,
			 "RX mailbox IRQ disabled at trace limit irq_count=%d\n", count);
		return IRQ_HANDLED;
	}
	ret = rx1619_snapshot_frame(rx->regmap, rx->power_good, &rx->pg_irqs, epoch,
				    &frame, &command, &pg_before, &pg_after);
	/* No ACK in observe: mask this dedicated mailbox IRQ at the first stable
	 * sample rather than tracing retries. PG and LN8282 observation continue.
	 */
	if (!ret)
		disable_irq_nosync(irq);
	if (!ret && command == RX1619_MAILBOX_CMD_10) {
		dev_info(rx->dev,
			 "RX mailbox irq_count=%d pg_before=%d pg_after=%d "
			 "cmd=0x10 rc=0 mailbox_payload=%02x:%02x:%02x:%02x pg_epoch=%d mailbox_masked=1\n",
			 count, pg_before, pg_after, frame.data[0],
			 frame.data[1], frame.data[2], frame.data[3], epoch);
	} else if (!ret) {
		dev_info(rx->dev,
			 "RX mailbox irq_count=%d pg_before=%d pg_after=%d cmd=0x%02x rc=0 "
			 "profile=%s capability_raw=%u fw=0x%02x pg_epoch=%d mailbox_masked=1\n",
			 count, pg_before, pg_after, command,
			 frame.data[0] & 0x80 ? "EPP" : "BPP", frame.data[0] & 0x7f, frame.data[3], epoch);
	} else {
		if (command == RX1619_MAILBOX_CMD_UNKNOWN)
			dev_info(rx->dev,
				 "RX mailbox irq_count=%d pg_before=%d pg_after=%d "
				 "cmd=unknown rc=%d pg_epoch=%d\n",
				 count, pg_before, pg_after, ret, epoch);
		else
			dev_info(rx->dev,
				 "RX mailbox irq_count=%d pg_before=%d pg_after=%d "
				 "cmd=0x%02x rc=%d pg_epoch=%d\n",
				 count, pg_before, pg_after, command, ret, epoch);
	}
	return IRQ_HANDLED;
}

#ifdef CONFIG_UMI_RX_LINK
static const struct power_supply_desc rx1619_supply;

/* Leave one notification pending until consumed by the shared-input arbiter.
 * A stuck or unsupported frame cannot generate an unbounded IRQ storm.
 */
static irqreturn_t rx1619_link_irq(int irq, void *data)
{
	struct rx1619 *rx = data;

	if (atomic_xchg(&rx->armed, 0))
		disable_irq_nosync(irq);
	power_supply_changed(rx->supply);
	return IRQ_HANDLED;
}

struct rx1619_transfer {
	struct rx1619 *rx;
	int (*check_input)(void *, bool);
	void *ctx;
	int epoch;
};

static int rx1619_link_check(struct rx1619_transfer *t, bool bpp)
{
	int ret;

	if (atomic_read(&t->rx->pg_irqs) != t->epoch)
		return -ENOLINK;
	ret = t->check_input(t->ctx, bpp);

	if (ret)
		return ret;
	ret = gpiod_get_value_cansleep(t->rx->power_good);
	if (ret < 0)
		return ret;
	return ret && atomic_read(&t->rx->pg_irqs) == t->epoch ? 0 : -ENOLINK;
}

static int rx1619_link_write(struct rx1619_transfer *t, unsigned int reg, unsigned int val)
{
	int ret = rx1619_link_check(t, false);
	return ret ? ret : regmap_write(t->rx->regmap, reg, val);
}

/* Same private Qi messages as the LOS receiver, not wired USB/PD messages.
 * RX firmware does authentication. AP requests the ID, UUID and adapter type;
 * none of these replies is a grant to change output voltage or pump state.
 */
enum { RX_ID_IDLE, RX_ID_WAIT_AUTH, RX_ID_WAIT_UUID, RX_ID_WAIT_TYPE };

static int rx1619_ident_reply(struct rx1619_transfer *t, const struct rx1619_frame *f)
{
	struct rx1619 *rx = t->rx;
	unsigned int next, cmd, result = 0;
	int ret;

	/* LOS consumes auth result/adapter type after the receive ACK settles. */
	if (f->cmd == 5 || f->cmd == 6) {
		ret = regmap_read(rx->regmap, RX1619_MAILBOX_FLAGS, &result);
		if (ret)
			return ret;
#ifdef CONFIG_UMI_RX_BUCK
		/* Never promote another frame's post-ACK byte to a power grant. */
		if (result != f->data[0]) return -EPROTO;
#endif
		ret = rx1619_link_check(t, false);
		if (ret)
			return ret;
	}
	switch (f->cmd) {
	case 4:
#ifdef CONFIG_UMI_RX_EPP
		if (rx->adapter) return -EPROTO; /* No stale adapter caps on re-auth. */
#endif
		rx->adapter = 0;
		cmd = 0x86;
		next = RX_ID_WAIT_AUTH;
		break;
	case 5:
		if (rx->ident_stage != RX_ID_WAIT_AUTH || !rx->fod)
			return -EPROTO;
		if (result != 1) {
			rx->ident_stage = RX_ID_IDLE;
			return 0;
		}
		cmd = 0x90;
		next = RX_ID_WAIT_UUID;
		break;
	case 0x0d:
		if (rx->ident_stage != RX_ID_WAIT_UUID)
			return -EPROTO;
#ifdef CONFIG_UMI_RX_EPP
		rx->car = rx->epp && f->data[0] == 6 && f->data[1] == 2 &&
			  f->data[2] == 8 && f->data[3] == 1;
		rx->voice = rx->epp && f->data[0] == 9 && f->data[1] == 8 &&
			    f->data[2] == 6 && f->data[3] == 7;
#endif
		cmd = 0x87;
		next = RX_ID_WAIT_TYPE;
		break;
	case 6:
		if (rx->ident_stage != RX_ID_WAIT_TYPE)
			return -EPROTO;
#ifdef CONFIG_UMI_RX_EPP
		if (rx->voice) result = 13;
		else if (rx->car && result >= 9) result = 11;
		ret = umi_rx_epp_event(t->ctx, 6, result, t->epoch);
		if (ret)
			return ret;
#endif
		rx->adapter = result;
		rx->ident_stage = RX_ID_IDLE;
		dev_info(rx->dev, "wireless TX adapter type=0x%02x\n", rx->adapter);
		return 0;
	default:
		return -EINVAL;
	}
	ret = rx1619_link_write(t, 0, cmd);
	if (!ret && cmd == 0x90)
		ret = rx1619_link_write(t, 1, rx->epp ? 0x4c : 0x3f);
	if (!ret)
		ret = rx1619_link_write(t, 0x0c, 0x55);
	if (!ret)
		rx->ident_stage = next;
	return ret;
}

/* LOS NuVolta rx1619_set_fod_param / rx1619_wireless_int_work, 71b13e62.
 * fod counts *submitted* groups; neither doorbell nor calibration grants power.
 */
static int rx1619_link_reply(struct rx1619_transfer *t, const struct rx1619_frame *f)
{
	static const unsigned char fod[][2] = {{0x44, 0x64}, {0x44, 0x78}, {0x3a, 0x67}, {0x37, 0x67}};
	unsigned int group = t->rx->fod;
	int ret;

	if ((f->cmd == 1 && group) || (f->cmd == 2 && !group) ||
	    (f->cmd == 3 && group != ARRAY_SIZE(fod)))
		return -EPROTO;
	ret = rx1619_link_write(t, 0x0c, 0xaa);
	if (ret)
		return ret;
	if (f->cmd != 2 && f->cmd != 0x0d)
		msleep(10);
#ifdef CONFIG_UMI_RX_EPP
	if (f->cmd == 1 || f->cmd == 3) {
		ret = rx1619_link_check(t, false);
		if (!ret)
			ret = umi_rx_epp_event(t->ctx, f->cmd, f->data[0], t->epoch);
		if (ret)
			return ret;
	}
#endif
	if (f->cmd == 0x10 || f->cmd == 3)
		return 0;
	if (f->cmd >= 4)
		return rx1619_ident_reply(t, f);
	if (f->cmd == 1)
		t->rx->epp = !!(f->data[0] & 0x80);
	if (f->cmd == 1 && !t->rx->epp) {
		ret = rx1619_link_check(t, true);
		if (ret)
			return ret;
	}
	if (group == ARRAY_SIZE(fod))
		return 0;
	ret = rx1619_link_write(t, 0x00, 0x85);
	if (!ret) ret = rx1619_link_write(t, 0x01, group + 1);
	if (!ret) ret = rx1619_link_write(t, 0x02, fod[group][0]);
	if (!ret) ret = rx1619_link_write(t, 0x03, fod[group][1]);
	if (!ret) ret = rx1619_link_write(t, 0x0c, 0x55);
	if (!ret) t->rx->fod++;
#ifdef CONFIG_UMI_RX_EPP
	if (!ret && f->cmd == 1)
		ret = umi_rx_epp_event(t->ctx, 2, 0, t->epoch);
#endif
	return ret;
}

static void rx1619_sync_link_epoch(struct rx1619 *rx, int epoch)
{
	if (rx->link_epoch == epoch)
		return;
	rx->link_epoch = epoch;
	rx->fod = rx->link_events = rx->adapter = 0;
	rx->ident_stage = RX_ID_IDLE;
	rx->epp = false;
	rx->started = rx->blocked = rx->resume_after_preselect = false;
#ifdef CONFIG_UMI_RX_BUCK
	rx->preselect_tx_id = false;
#endif
}

#ifdef CONFIG_UMI_RX_BUCK
/* Early polling and IRQ service share the one TX ID attempt per PG epoch. */
static int rx1619_ack_preselect_tx_id(struct rx1619_transfer *t,
				     const struct rx1619_frame *frame)
{
	struct rx1619 *rx = t->rx;
	int ret = rx1619_link_check(t, false);

	if (ret)
		return ret;
	/* A failed transfer may still have acknowledged the frame. */
	rx->preselect_tx_id = true;
	ret = regmap_write(rx->regmap, 0x0c, 0xaa);
	if (ret)
		rx->blocked = true;
	dev_info(rx->dev, "wireless RX preselect TX ID=%02x:%02x epoch=%d rc=%d\n",
		 frame->data[0], frame->data[1], t->epoch, ret);
	return ret;
}

int umi_rx1619_preselect_tx_id(struct power_supply *psy, int epoch,
			       int (*guard)(void *, bool), void *ctx)
{
	struct rx1619_frame frame;
	struct rx1619_transfer tx;
	struct rx1619 *rx;
	unsigned int cmd;
	int before, after, ret;

	if (psy->desc != &rx1619_supply)
		return -ENODEV;
	rx = power_supply_get_drvdata(psy);
	if (epoch != atomic_read(&rx->pg_irqs))
		return -ENOLINK;
	rx1619_sync_link_epoch(rx, epoch);
	if (rx->blocked)
		return -ENOLINK;
	if (rx->preselect_tx_id)
		return 0;
	/* Once the shared service has primed/armed its IRQ, it owns mailbox
	 * dispatch. Keep the bounded owner wait alive while it handles late TX ID. */
	if (atomic_read(&rx->armed) || rx->started)
		return 0;

	ret = regmap_read(rx->regmap, RX1619_MAILBOX_CMD, &cmd);
	if (ret || cmd != RX1619_MAILBOX_CMD_10)
		return ret;
	ret = rx1619_snapshot_frame(rx->regmap, rx->power_good, &rx->pg_irqs,
				    epoch, &frame, &cmd, &before, &after);
	if (ret == -ENODATA || ret == -EAGAIN)
		return 0;
	if (ret || frame.cmd != RX1619_MAILBOX_CMD_10)
		return ret;

	tx = (struct rx1619_transfer){rx, guard, ctx, epoch};
	return rx1619_ack_preselect_tx_id(&tx, &frame);
}
#endif

static int rx1619_service(struct power_supply *psy,
			  int (*check_input)(void *, bool), void *ctx,
			  bool poll_armed)
{
	struct rx1619_frame f;
	struct rx1619 *rx;
	unsigned int cmd = RX1619_MAILBOX_CMD_UNKNOWN;
	int epoch, irq, before, after, ret = 0;
	bool armed;

	if (psy->desc != &rx1619_supply)
		return -ENODEV;
	rx = power_supply_get_drvdata(psy);
	irq = smp_load_acquire(&rx->link_irq);
	if (!irq)
		return -EAGAIN;
	epoch = atomic_read(&rx->pg_irqs);
	rx1619_sync_link_epoch(rx, epoch);
	if (!check_input || rx->blocked)
		goto stop;
	/* No replay on the periodic SMB5 poll. Prime once on a new session to
	 * cover docking before probe/ownership; subsequently require an IRQ.
	 */
	armed = atomic_read(&rx->armed);
	if (rx->started && armed && !poll_armed && !rx->resume_after_preselect)
		return 0;
	rx->resume_after_preselect = false;
	rx->started = true;
	/* An ACK that never clears must not replay indefinitely. */
	ret = !armed && ++rx->link_events > RX1619_MAILBOX_TRACE_MAX ?
		-ELOOP : check_input(ctx, false);
	if (ret)
		goto stop;
	/* During battery-inhibited preselection the shared IRQ may miss a mailbox
	 * edge. Poll its doorbell while armed; read a full stable frame only when
	 * a command is pending. Normal link service remains IRQ-driven. */
	if (poll_armed && armed) {
		ret = regmap_read(rx->regmap, RX1619_MAILBOX_CMD, &cmd);
		if (ret)
			goto stop;
		if (!cmd || (rx->preselect_tx_id && cmd == RX1619_MAILBOX_CMD_10))
			return 0;
	}
	/* Arm before reading: an empty mailbox racing its first event wakes us.
	 * Do not dispatch an unstable sample if a new edge arrives during reads.
	 */
	synchronize_irq(irq);
	if (!atomic_xchg(&rx->armed, 1))
		enable_irq(irq);
	ret = rx1619_snapshot_frame(rx->regmap, rx->power_good, &rx->pg_irqs, epoch,
				    &f, &cmd, &before, &after);
	if (poll_armed && ret == -EAGAIN && epoch == atomic_read(&rx->pg_irqs))
		return 0; /* Mailbox changed mid-sample; the bounded preselect loop retries. */
	if (ret == -ENODATA && cmd == 0)
		return 0;
	if (!ret && !atomic_read(&rx->armed)) {
		if (poll_armed && epoch == atomic_read(&rx->pg_irqs))
			return 0; /* A stable frame raced its IRQ; retry in preselection. */
		ret = -EAGAIN;
	}
#ifdef CONFIG_UMI_RX_BUCK
	if (!ret && rx->preselect_tx_id && f.cmd == RX1619_MAILBOX_CMD_10)
		return 0;
#endif
	if (!ret) {
		struct rx1619_transfer t = {rx, check_input, ctx, epoch};

#ifdef CONFIG_UMI_RX_BUCK
		if (poll_armed && f.cmd == RX1619_MAILBOX_CMD_10) {
			ret = rx1619_ack_preselect_tx_id(&t, &f);
			if (ret)
				goto stop;
			return 0;
		}
		/* Authentication starts after the shared charger qualifies USBIN. */
		if (poll_armed && f.cmd > 3) {
			rx->resume_after_preselect = true;
			return 0;
		}
#endif
		ret = rx1619_link_reply(&t, &f);
		if (ret && poll_armed)
			dev_info(rx->dev, "wireless RX preselect mailbox cmd=%#x epoch=%d rc=%d\n",
				 f.cmd, epoch, ret);
		if (!ret && f.cmd == 0x10)
			dev_info(rx->dev, "wireless RX TX ID=%02x:%02x\n", f.data[0], f.data[1]);
		if (!ret && f.cmd == 3)
			dev_info(rx->dev, "wireless RX calibrated after four FOD groups\n");
		if (!ret && f.cmd == 1)
			dev_info(rx->dev, "wireless RX LDO %s capability=%u\n",
				 f.data[0] & 0x80 ? "EPP" : "BPP", f.data[0] & 0x7f);
	}
	if (!ret)
		return 0;
stop:
	/* An ambiguous partial write is never retried in this PG epoch. */
	rx->blocked |= rx->started;
#ifdef CONFIG_UMI_RX_BUCK
	rx->blocked |= rx->preselect_tx_id;
#endif
	if (atomic_xchg(&rx->armed, 0))
		disable_irq_nosync(irq);
	return ret;
}

int umi_rx1619_service(struct power_supply *psy,
		       int (*check_input)(void *, bool), void *ctx)
{
	return rx1619_service(psy, check_input, ctx, false);
}

#ifdef CONFIG_UMI_RX_BUCK
int umi_rx1619_preselect_service(struct power_supply *psy,
				int (*check_input)(void *, bool), void *ctx)
{
	return rx1619_service(psy, check_input, ctx, true);
}
#endif
#endif

static int rx1619_mailbox_init(struct i2c_client *client, struct rx1619 *rx)
{
	int ret;

#ifdef CONFIG_UMI_RX_LINK
	if (client->irq <= 0)
		return -ENXIO;
	ret = devm_request_threaded_irq(rx->dev, client->irq, NULL, rx1619_link_irq,
					IRQF_ONESHOT | IRQF_NO_AUTOEN, dev_name(rx->dev), rx);
	if (!ret)
		smp_store_release(&rx->link_irq, client->irq);
	return ret;
#endif
	if (!RX1619_TRACE_ENABLED)
		return 0;
	if (client->irq <= 0)
		return -ENXIO;
	ret = devm_request_threaded_irq(&client->dev, client->irq, NULL, rx1619_mailbox_changed,
					IRQF_ONESHOT, dev_name(&client->dev), rx);
	if (!ret)
		dev_info(rx->dev, "RX mailbox IRQ installed irq=%d\n", client->irq);
	return ret;
}

#endif
