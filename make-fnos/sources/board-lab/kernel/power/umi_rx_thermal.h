/* SPDX-License-Identifier: GPL-2.0-only */
/* Umi thermal-normal.conf monitor and LineageOS 71b13e62 umi-sm8250.dtsi.
 * Table entries in mA, converted back to power_supply microamps at use.
 */
#ifndef UMI_RX_THERMAL_H
#define UMI_RX_THERMAL_H

static inline int umi_rx_level(int *step, const int mc[6], int screen)
{
	static const int weight[] = {223, 150, 440, -143, 115, 149};
	static const int up[] = {40000,41500,43000,43800,44600,45400,46200,47000};
	static const int down[] = {38000,40000,41500,43000,43800,44600,45400,46200};
	static const int on[] = {0,4,6,8,8,8,10,10,13};
	static const int off[] = {0,0,0,2,4,6,8,10,13};
	long long sum = 0;
	int i, t, n = *step;

	if (n < 0 || n > 8)
		return -ERANGE;
	for (i = 0; i < 6; i++) {
		if (mc[i] <= -40000 || mc[i] >= 125000)
			return -ERANGE;
		sum += (long long)mc[i] * weight[i];
	}
	t = sum / 1000 + 4541;
	while (n < 8 && t >= up[n]) n++;
	while (n && t < down[n - 1]) n--;
	*step = n;
	/* An unknown display state uses the stricter of the two OEM targets. */
	return screen == 0 ? off[n] : on[n];
}

static inline int umi_rx_caps(int adapter, bool epp, int level, int *icl, int *fcc)
{
	static const unsigned short dc[] = {
		6000, 4400, 4200, 3400, 3200, 2800, 2600, 2200,
		2000, 1100, 1000, 800, 700, 600, 500, 400};
	static const unsigned short dc_20w[] = {
		4000, 3400, 3200, 2800, 2600, 2200, 2000, 1100,
		1000, 800, 700, 600, 500, 500, 400, 300};
	static const unsigned short voice[] = {
		6000, 2200, 2200, 1000, 1000, 800, 800, 800,
		800, 700, 700, 600, 600, 600, 500, 400};
	static const unsigned short epp_table[] = {
		1800, 1800, 1800, 1300, 1300, 1300, 1300, 800,
		800, 600, 600, 500, 500, 500, 400, 300};
	static const unsigned short bpp[] = {
		850, 850, 850, 850, 850, 850, 850, 700,
		700, 500, 500, 500, 500, 500, 400, 300};
	static const unsigned short bpp_qc2[] = {
		1000, 1000, 1000, 1000, 1000, 1000, 1000, 700,
		700, 500, 500, 500, 500, 500, 400, 300};
	static const unsigned short bpp_qc3[] = {
		1100, 1100, 1100, 1100, 1100, 700, 700, 600,
		600, 500, 500, 500, 500, 500, 400, 300};
	const unsigned short *table = bpp;
	bool both = false;

	if (level < 0 || level > 15) return -ERANGE;
	switch (adapter) {
	case 9: case 10: case 11: table = dc_20w; both = true; break;
	case 12: case 14: case 15: case 16: table = dc; both = true; break;
	case 13: table = voice; both = true; break;
	case 5: table = bpp_qc2; break;
	case 6: table = epp ? epp_table : bpp_qc3; break;
	case 7: case 8: table = epp ? epp_table : bpp; break;
	}
	/* Zero means remove our ceiling, not program zero current. */
	*icl = level ? table[level] * 1000 : 0;
	*fcc = both ? *icl : 0;
	return 0;
}
#endif
