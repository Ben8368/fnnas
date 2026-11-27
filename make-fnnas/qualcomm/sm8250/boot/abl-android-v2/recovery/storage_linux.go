// SPDX-License-Identifier: GPL-2.0-only
package main

import (
	"crypto/sha256"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"
)

// Match this board's main UFS device, not a particular Linux /dev/sdX
// enumeration and never a host-selected disk, offset, or byte count.
const sectorBytes = 4096
const diskBytes int64 = 254778802176
const expectedModel = "SDINEDK4-256G"

var scsiDisk = regexp.MustCompile(`^sd[a-z]+$`)
var lunZero = regexp.MustCompile(`/[^/]*1d84000\.ufshc/.*\/[0-9]+:0:0:0(?:/|$)`)

func sysEquals(path, expected string) bool {
	text, err := os.ReadFile(path)
	return err == nil && strings.TrimSpace(string(text)) == expected
}

func ramOnlyMounts(text string) bool {
	seenRoot := false
	for _, line := range strings.Split(strings.TrimSpace(text), "\n") {
		left, right, ok := strings.Cut(line, " - ")
		names, meta := strings.Fields(left), strings.Fields(right)
		if !ok || len(names) < 6 || len(meta) < 3 {
			return false
		}
		switch meta[0] {
		case "rootfs", "ramfs", "tmpfs", "devtmpfs", "proc", "sysfs", "configfs":
		default:
			return false
		}
		if names[4] == "/" && (meta[0] == "rootfs" || meta[0] == "ramfs" || meta[0] == "tmpfs") {
			seenRoot = true
		}
	}
	return seenRoot
}

func gptDigests(disk io.ReaderAt) (string, error) {
	head := make([]byte, 6*sectorBytes)
	tail := make([]byte, 5*sectorBytes)
	for _, region := range []struct {
		buf []byte
		off int64
	}{
		{head, 0}, {tail, diskBytes - int64(len(tail))},
	} {
		if n, err := disk.ReadAt(region.buf, region.off); n != len(region.buf) || err != nil {
			return "", fmt.Errorf("cannot read full GPT metadata region at %d: %d bytes, %v", region.off, n, err)
		}
	}
	if string(head[sectorBytes:sectorBytes+8]) != "EFI PART" || string(tail[len(tail)-sectorBytes:len(tail)-sectorBytes+8]) != "EFI PART" {
		return "", fmt.Errorf("both GPT headers must be present")
	}
	return fmt.Sprintf("%x %x", sha256.Sum256(head), sha256.Sum256(tail)), nil
}

func umiGPTInventory() (string, error) {
	if err := virtualMount("proc", "/proc"); err != nil {
		return "", err
	}
	mounts, err := os.ReadFile("/proc/self/mountinfo")
	if err != nil || !ramOnlyMounts(string(mounts)) {
		return "", fmt.Errorf("cannot prove that only RAM and virtual filesystems are mounted")
	}
	for attempt := 0; attempt < 15; attempt++ {
		names, err := os.ReadDir("/sys/class/block")
		if err != nil {
			return "", err
		}
		var candidates []string
		for _, entry := range names {
			name := entry.Name()
			if !scsiDisk.MatchString(name) {
				continue
			}
			sys := filepath.Join("/sys/class/block", name)
			device, err := filepath.EvalSymlinks(sys)
			if err == nil && lunZero.MatchString(device) &&
				sysEquals(sys+"/device/model", expectedModel) &&
				sysEquals(sys+"/size", fmt.Sprint(diskBytes/512)) &&
				sysEquals(sys+"/queue/logical_block_size", fmt.Sprint(sectorBytes)) {
				candidates = append(candidates, name)
			}
		}
		if len(candidates) > 1 {
			return "", fmt.Errorf("ambiguous Umi main UFS LUN")
		}
		if len(candidates) == 1 {
			name := candidates[0]
			disk, err := os.OpenFile(filepath.Join("/dev", name), os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
			if err != nil {
				return "", err
			}
			defer disk.Close()
			info, err := disk.Stat()
			if err != nil || info.Mode()&os.ModeDevice == 0 || info.Mode()&os.ModeCharDevice != 0 {
				return "", fmt.Errorf("Umi main UFS LUN is not a block device")
			}
			facts, err := gptDigests(disk)
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("%s %d %d ram-only %s", name, diskBytes, sectorBytes, facts), nil
		}
		time.Sleep(time.Second)
	}
	return "", fmt.Errorf("matching Umi main UFS LUN did not appear")
}
