# 小米 10 独立 RAM Recovery（开发预览）

当前只实现 **电脑 → USB ACM → Recovery → SHA-256 回执**。Recovery 用独立 initramfs 和 PID 1，不继承 fnOS 的 initramfs 或根分区参数。它只挂载内核虚拟文件系统，不打开任何持久化文件系统或块设备，不提供 shell、安装、OTA 或回滚功能。设备端只对输入计算摘要，然后丢弃字节，不解包、不保存、不执行。每次启动只接收一次请求，最多 **64 MiB**，从 PID 1 启动起约 **180 秒**尝试重启回原系统，即使 USB 没有枚举、传输中断或校验失败也一样。这不是正式发行镜像。

## 1. 在本地构建

从已验证的原生 fnOS `native` 或获准的 `native-debug` 目录取 `boot.img`，核对其 `SHA256SUMS` 和内核晋级/候选记录。不要使用 Debian 重现镜像或未验证的启动镜像。构建需要 Python 3.11+ 和 Go 1.23+，不需要联网下载 Go 模块，无须连接设备。下面的变量由维护者填写：

```bash
TOOLS=make-fnnas/qualcomm/sm8250/boot/abl-android-v2/recovery
NATIVE=/path/to/local-native-build
BOOT_SHA="<boot.img SHA-256 from the native SHA256SUMS>"
python3 -B "$TOOLS/build-recovery.py" "$NATIVE/boot.img" ./recovery-ram.img --boot-sha256 "$BOOT_SHA"
```

构建器保留输入内核和 DTB 的原始字节，仅更换 initramfs、移除持久根参数，并打印新镜像 SHA-256。留存新镜像摘要、原生 boot 摘要、源码和 Linux 提交、内核配置、CI Run/Attempt 和包摘要。生成的镜像只留本地；对外分发前另做内核和 Go 静态依赖的许可及对应源码审计。

## 2. 获准后在真机验证

1. 记录当前可启动系统和基线状态。确认维护者批准这次 RAM 启动、已准备回到原系统，且面板与内核档位匹配。
2. 从同一台设备只读核对当前活动的原厂 DTBO 及索引。对 **本次 `recovery-ram.img`** 解包后的 `dtb`，按[真机无刷写验收](04-真机无刷写验收.md)运行 `check-installed-dtbo.py --protect-live`。对于 `native-debug` 还需比对构建目录中的 `stock-dtbo.txt`。预检失败就停止，不修改 DTBO 或其他分区。
3. 从原系统进入 Fastboot，记录目标序列号并确认 `fastboot -s "$SERIAL" getvar product` 为 `umi`。复核镜像摘要，只执行 `fastboot -s "$SERIAL" boot ./recovery-ram.img`，**不要执行任何 `fastboot flash`**。
4. 找到新枚举的 `UMI-RAM-RECOVERY` ACM 端口（Linux `/dev/ttyACM*`、macOS `/dev/cu.usbmodem*`、Windows `COMx`）。不要让串口终端、日志收集器或自动串口探测程序同时占用它。主机 Python 环境需要 `pyserial==3.5`。先发送小的非敏感二进制夹具，再另起一轮测试较大的输入：

```bash
python3 -B "$TOOLS/send-recovery.py" --port "$PORT" --boot-sha256 "$BOOT_SHA" ./input.bin
```

成功时打印 JSON 回执：协议版本、原生 boot 摘要、本次随机标识、接收字节数和 SHA-256。主机在收到匹配的 `READY` 前不会发送文件内容；只有收到匹配的 `RESULT` 才成功退出。摘要证明两端传输字节一致，不是签名或设备身份认证。发送端不自动选端口、不自动重试，也不调用 Fastboot；任何传输错误都等设备回到原系统后再开新一轮。

5. 保留回执，观察设备重启并验证回到**同一套原系统**。如果超时未恢复，按原系统的非写入恢复流程操作，不尝试刷写。本次验收只记为「RAM Recovery 输入链路」，不改变内核、fnOS 用户态或 OTA 的验收状态。

## 下一道门槛

先拿到真机上小文件、较大文件和断线后返回原系统的记录。再引入**不写盘**的 `rootfs.img.zst` 流式解压验证：限定展开大小、校验压缩与解压后的摘要、测量吞吐并验证中断行为。之后才单独设计获准写盘、能验证目标分区、可诊断中断，并明确 Boot/RootFS 配对的安装流程；OTA 另行验收。
