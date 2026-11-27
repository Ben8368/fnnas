// SPDX-License-Identifier: GPL-2.0-only
package main

import (
	"bytes"
	"fmt"
	"io"
	"testing"
)

type fixtureDisk struct {
	badHeader bool
	shortTail bool
}

func (f fixtureDisk) ReadAt(buf []byte, offset int64) (int, error) {
	switch offset {
	case 0:
		if !f.badHeader {
			copy(buf[sectorBytes:], "EFI PART")
		}
	case diskBytes - 5*sectorBytes:
		if f.shortTail {
			return 0, io.EOF
		}
		copy(buf[4*sectorBytes:], "EFI PART")
	default:
		return 0, io.EOF
	}
	return len(buf), nil
}

func TestReadOnlyGPT(t *testing.T) {
	if !lunZero.MatchString("/sys/devices/platform/soc@0/1d84000.ufshc/host0/target0:0:0/0:0:0:0/block/sda") ||
		lunZero.MatchString("/sys/devices/platform/soc@0/1d84000.ufshc/host0/target0:0:0/0:0:0:4/block/sde") {
		t.Fatal("wrong UFS LUN matching")
	}
	if !ramOnlyMounts("1 0 0:1 / / rw - rootfs rootfs rw\n2 1 0:2 / /dev rw - devtmpfs devtmpfs rw\n") ||
		ramOnlyMounts("1 0 8:34 / / rw - btrfs /dev/sda34 rw\n") || ramOnlyMounts("") {
		t.Fatal("wrong mount policy")
	}
	want, err := gptDigests(fixtureDisk{})
	if err != nil || len(want) != 129 {
		t.Fatalf("invalid digest result: %q, %v", want, err)
	}
	for _, invalid := range []fixtureDisk{{badHeader: true}, {shortTail: true}} {
		if _, err := gptDigests(invalid); err == nil {
			t.Fatal("accepted incomplete GPT")
		}
	}
	var output bytes.Buffer
	input := bytes.NewBufferString(fmt.Sprintf("%s GPT %s\n", protocol, nonce))
	if err := receive(peer{input, &output}, baseDigest, func() (string, error) { return want, nil }); err != nil {
		t.Fatal(err)
	}
	if output.String() != fmt.Sprintf("%s GPT-RESULT %s %s %s\n", protocol, nonce, baseDigest, want) {
		t.Fatal("unbound recovery result")
	}
	input = bytes.NewBufferString(fmt.Sprintf("%s GPT %s /dev/sde\n", protocol, nonce))
	if err := receive(peer{input, &output}, baseDigest, func() (string, error) { t.Fatal("unexpected read"); return "", nil }); err == nil {
		t.Fatal("accepted a host-selected disk")
	}
}
