// SPDX-License-Identifier: GPL-2.0-only
package main

import (
	"os"
	"testing"
)

// The cross-architecture PTY regression drives this exact receive function
// from the Python host program, without exposing this entry point in PID 1.
func TestStdioPeer(t *testing.T) {
	if os.Getenv("UMI_RECOVERY_STDIO") != "1" {
		t.Skip("host integration peer")
	}
	if err := setRaw(os.Stdin); err != nil {
		t.Fatal(err)
	}
	if err := receive(peer{os.Stdin, os.Stdout}, baseDigest, nil); err != nil {
		t.Fatal(err)
	}
}
