// SPDX-License-Identifier: GPL-2.0-only
package main

import (
	"bytes"
	"crypto/sha256"
	"fmt"
	"io"
	"strings"
	"testing"
)

const nonce = "0123456789abcdef0123456789abcdef"

var baseDigest = strings.Repeat("a", 64)

type peer struct {
	io.Reader
	io.Writer
}

func TestReceive(t *testing.T) {
	for _, data := range [][]byte{nil, bytes.Repeat([]byte{0, 10, 13, 17, 19, 255}, 16000)} {
		input := fmt.Appendf(nil, "%s HASH %s %d\n", protocol, nonce, len(data))
		var output bytes.Buffer
		if err := receive(peer{bytes.NewReader(append(input, data...)), &output}, baseDigest, nil); err != nil {
			t.Fatal(err)
		}
		want := fmt.Sprintf("%s READY %s %s\n%s RESULT %s %d %x\n", protocol, nonce, baseDigest,
			protocol, nonce, len(data), sha256.Sum256(data))
		if output.String() != want {
			t.Fatalf("got %q; want %q", &output, want)
		}
	}
}

func TestReject(t *testing.T) {
	for _, bad := range []string{
		"", strings.Repeat("x", 128) + "\n", protocol + " EXEC " + nonce + " 0\n", protocol + " HASH not-a-nonce 0\n",
		protocol + " HASH " + nonce + " +0\n", protocol + " HASH " + nonce + " 18446744073709551616\n",
		fmt.Sprintf("%s HASH %s %d\n", protocol, nonce, maxPayload+1),
	} {
		var output bytes.Buffer
		if err := receive(peer{strings.NewReader(bad), &output}, baseDigest, nil); err == nil || output.Len() != 0 {
			t.Fatalf("request %q not rejected: %q, %v", bad, &output, err)
		}
	}
	var output bytes.Buffer
	if err := receive(peer{strings.NewReader(protocol + " HASH " + nonce + " 3\na"), &output}, baseDigest, nil); err == nil ||
		strings.Contains(output.String(), " RESULT ") {
		t.Fatalf("short input yielded a receipt: %q, %v", &output, err)
	}
}
