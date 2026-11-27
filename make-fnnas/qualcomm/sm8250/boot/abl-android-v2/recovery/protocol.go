// SPDX-License-Identifier: GPL-2.0-only
package main

import (
	"bufio"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
)

const (
	protocol   = "FNNAS-UMI-RECOVERY/1"
	maxPayload = 64 << 20
)

func isHex(s string, size int) bool {
	if len(s) != size {
		return false
	}
	for _, c := range s {
		if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'f') {
			return false
		}
	}
	return true
}

// One request per boot. The payload is hashed and discarded; it is never
// interpreted, decompressed, saved, mounted, or passed to another process.
func receive(rw io.ReadWriter, bootDigest string) error {
	reader := bufio.NewReaderSize(rw, 128)
	line, err := reader.ReadSlice('\n')
	if err != nil {
		return fmt.Errorf("request: %w", err)
	}
	fields := strings.Split(string(line[:len(line)-1]), " ")
	if len(fields) != 4 || fields[0] != protocol || fields[1] != "HASH" || !isHex(fields[2], 32) {
		return errors.New("bad request header")
	}
	count, err := strconv.ParseUint(fields[3], 10, 64)
	if err != nil || count > maxPayload || strconv.FormatUint(count, 10) != fields[3] {
		return errors.New("bad payload size")
	}
	if _, err := fmt.Fprintf(rw, "%s READY %s %s\n", protocol, fields[2], bootDigest); err != nil {
		return err
	}
	hash := sha256.New()
	if _, err := io.CopyN(hash, reader, int64(count)); err != nil {
		return fmt.Errorf("incomplete payload: %w", err)
	}
	_, err = fmt.Fprintf(rw, "%s RESULT %s %d %x\n", protocol, fields[2], count, hash.Sum(nil))
	return err
}
