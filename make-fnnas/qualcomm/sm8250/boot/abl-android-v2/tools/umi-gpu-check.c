// SPDX-License-Identifier: GPL-2.0-only
/* Query the initialized MSM GPU through a render node, with no display master. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <drm/msm_drm.h>

int main(int argc, char **argv)
{
	int i;

	for (i = 1; i < argc; i++) {
		struct drm_msm_param chip = {
			.pipe = MSM_PIPE_3D0,
			.param = MSM_PARAM_CHIP_ID,
		};
		int fd = open(argv[i], O_RDWR | O_CLOEXEC);

		if (fd < 0) {
			printf("GPU %s open=%s\n", argv[i], strerror(errno));
			continue;
		}
		if (ioctl(fd, DRM_IOCTL_MSM_GET_PARAM, &chip) < 0) {
			printf("GPU %s MSM_PARAM_CHIP_ID=%s\n", argv[i], strerror(errno));
			close(fd);
			continue;
		}
		close(fd);
		printf("GPU %s chip_id=0x%08" PRIx64 "\n", argv[i], (uint64_t)chip.value);
		return 0;
	}

	puts("GPU MSM initialization query failed");
	return 1;
}
