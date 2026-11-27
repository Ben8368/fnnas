# 小米 10 原生 fnOS 真机验收

本目录的 `boot.img` 对应 `boot`，`rootfs.img` 是直接写入 `userdata` 的 Btrfs 文件系统镜像。两者使用同一个根文件系统 UUID，须成对使用。`kernel-candidate.json` 记录源码、Linux 提交、CI Run/Attempt 和包摘要。`stock-dtbo.txt` 记录构建时通过检查的原厂 DTBO 摘要和活动索引。

## 安装前

1. 确认设备为已解锁的小米 10（Umi）CSOT，已经备份现有数据并准备了该机的恢复方案。写入 `userdata` 会覆盖原系统和数据。安装须经设备维护者确认。
2. 确认该设备当前活动的原厂 DTBO 与 `stock-dtbo.txt` 一致。用从同一设备读回的 DTBO 核对摘要，并核对活动索引。安装只写 `boot` 和 `userdata`。
3. 在镜像目录核对文件摘要。Linux 用 `sha256sum -c SHA256SUMS`，macOS 用 `shasum -a 256 -c SHA256SUMS`。使用新版 Android Platform Tools，将 `SERIAL` 设为 `fastboot devices` 显示的目标设备序列号。

```bash
fastboot -s "$SERIAL" getvar product
fastboot -s "$SERIAL" getvar partition-size:boot
fastboot -s "$SERIAL" getvar partition-size:userdata
wc -c boot.img rootfs.img
```

确认 `product` 为 `umi`，并确认两个镜像的字节数分别小于或等于对应的分区大小。Fastboot 的分区大小通常以十六进制显示。

## 写入并启动

```bash
fastboot -s "$SERIAL" flash userdata rootfs.img &&
  fastboot -s "$SERIAL" flash boot boot.img &&
  fastboot -s "$SERIAL" reboot
```

## 验收 fnOS

- 未建账号时先检验 USB：电脑同时发现 NCM 网卡和 ACM 串口；串口不用输入任何内容即可捕获完整 `UMI_BOOTLOG/1` 帧，且不出现 getty 或 shell。记录帧中的内核、根文件系统类型、DTBO 核验信息及 USB 地址。拔插后确认串口继续输出、网络可以重新连接。
- 首次配置：记录电脑是否从 USB DHCP 得到 `172.16.42.2/24`，USB 链路不应下发默认网关或 DNS。打开 <http://172.16.42.1:5666>，验证首次建管理员账号并登录。仅 DHCP 失败时，在已识别的 USB 网卡上临时手配该地址并单独记录。用授权管理会话记录 `uname -r`、`findmnt -no SOURCE,FSTYPE,OPTIONS /`、`systemctl --failed`，从 `/etc/umi-build/kernel-candidate.json` 核对候选。
- 存储。记录 fnOS 界面识别的磁盘和容量。在获准使用的测试盘上验证小文件写入、读回及重启后仍可读取。
- 重启与恢复。从已安装的 fnOS 请求进入 Fastboot，确认目标设备成功枚举，再重启回同一套 fnOS 并复查登录和存储。保留启动日志、镜像摘要及 CI 标识。分别记录内核、fnOS 用户态和 OTA 的实际验收结果。
