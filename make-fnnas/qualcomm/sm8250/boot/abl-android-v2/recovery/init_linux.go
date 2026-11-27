// SPDX-License-Identifier: GPL-2.0-only
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const gadget = "/sys/kernel/config/usb_gadget/umi_recovery"

func log(message string) {
	if f, err := os.OpenFile("/dev/kmsg", os.O_WRONLY, 0); err == nil {
		defer f.Close()
		fmt.Fprintln(f, "<5>UMI_RECOVERY:", message)
	}
}

func virtualMount(source, target string) error {
	if err := os.MkdirAll(target, 0755); err != nil {
		return err
	}
	return syscall.Mount(source, target, source, syscall.MS_NOSUID|syscall.MS_NOEXEC, "")
}

func configure() error {
	if err := virtualMount("sysfs", "/sys"); err != nil {
		return err
	}
	if err := virtualMount("configfs", "/sys/kernel/config"); err != nil {
		return err
	}
	for _, dir := range []string{"", "strings/0x409", "configs/c.1", "functions/acm.usb0"} {
		if err := os.Mkdir(filepath.Join(gadget, dir), 0755); err != nil {
			return err
		}
	}
	// Local lab use only, consistent with the Umi RAM probe. This is not a
	// USB VID/PID allocation for shipping a product.
	for name, value := range map[string]string{
		"idVendor": "0x1d6b", "idProduct": "0x0104", "bDeviceClass": "0xef",
		"bDeviceSubClass": "0x02", "bDeviceProtocol": "0x01",
		"strings/0x409/product":      "FnNAS Umi RAM Recovery",
		"strings/0x409/manufacturer": "Local test",
		"strings/0x409/serialnumber": "UMI-RAM-RECOVERY",
	} {
		if err := os.WriteFile(filepath.Join(gadget, name), []byte(value+"\n"), 0644); err != nil {
			return err
		}
	}
	return os.Symlink(gadget+"/functions/acm.usb0", gadget+"/configs/c.1/acm.usb0")
}

func setRaw(tty *os.File) error {
	var term syscall.Termios
	raw, err := tty.SyscallConn()
	if err != nil {
		return err
	}
	var opErr syscall.Errno
	err = raw.Control(func(fd uintptr) {
		_, _, opErr = syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCGETS, uintptr(unsafe.Pointer(&term)))
		if opErr != 0 {
			return
		}
		term.Iflag, term.Oflag, term.Lflag = 0, 0, 0
		term.Cflag = (term.Cflag &^ (syscall.CSIZE | syscall.PARENB)) | syscall.CS8 | syscall.CREAD | syscall.CLOCAL
		term.Cc[syscall.VMIN], term.Cc[syscall.VTIME] = 1, 0
		_, _, opErr = syscall.Syscall(syscall.SYS_IOCTL, fd, syscall.TCSETS, uintptr(unsafe.Pointer(&term)))
	})
	if err != nil {
		return err
	}
	if opErr != 0 {
		return opErr
	}
	return nil
}

func run() error {
	identity, err := os.ReadFile("/boot-sha256")
	if err != nil {
		return err
	}
	digest := strings.TrimSuffix(string(identity), "\n")
	if !isHex(digest, 64) {
		return fmt.Errorf("invalid base boot identity")
	}
	if err := configure(); err != nil {
		return err
	}
	// Put the tty in raw mode before USB enumeration so the first bytes
	// cannot be echoed, line-edited, or interpreted as terminal signals.
	tty, err := os.OpenFile("/dev/ttyGS0", os.O_RDWR|syscall.O_NOCTTY|syscall.O_NONBLOCK, 0)
	if err != nil {
		return err
	}
	defer tty.Close()
	if err := setRaw(tty); err != nil {
		return err
	}
	var bound bool
	for i := 0; i < 12 && !bound; i++ {
		controllers, err := os.ReadDir("/sys/class/udc")
		if err == nil {
			for _, udc := range controllers {
				if os.WriteFile(gadget+"/UDC", []byte(udc.Name()+"\n"), 0644) == nil {
					bound = true
					break
				}
			}
		}
		if !bound {
			time.Sleep(time.Second)
		}
	}
	if !bound {
		return fmt.Errorf("no available USB device controller")
	}
	log("ACM ready; waiting for one read-only input transaction")
	if err := receive(tty, digest); err != nil {
		return err
	}
	log("input received and discarded; SHA-256 receipt sent")
	idle() // Keep ttyGS0 open until the deadline, including pending USB writes.
	return nil
}

func main() {
	if os.Getpid() != 1 {
		os.Exit(2)
	}
	// Independent of enumeration, framing, or a blocked/disconnected host.
	time.AfterFunc(180*time.Second, func() {
		_ = syscall.Reboot(syscall.LINUX_REBOOT_CMD_RESTART)
	})
	if err := virtualMount("devtmpfs", "/dev"); err == nil {
		log("RAM-only PID 1; no persistent filesystems are opened")
		if err := run(); err != nil {
			log(err.Error())
		}
	}
	// Never exit PID 1, even when gadget setup or reception failed.
	idle()
}

func idle() {
	for {
		time.Sleep(time.Minute)
	}
}
