# 小米 10 原生 fnOS 真机验收

本目录的 `boot.img` 和 `rootfs.img` 必须成对使用：两者绑定同一根 UUID，分别写入 `boot` 与 `userdata`。`kernel-candidate.json` 记录内核来源。默认构建还附有 LineageOS 官方 Umi 的 `dtbo.img` 和出处 `lineage-dtbo.json`，本次构建已对镜像的**每个** overlay 跑过保护性校验。旧的显式读回方式仅输出 `stock-dtbo.txt`。

## 安装前

1. 确认为已解锁的小米 10（Umi）CSOT，已有该机的恢复方案和必要备份，并获得本次写入授权。写入 `userdata` 会覆盖原系统与数据。
2. `sha256sum -c SHA256SUMS`（macOS 可用 `shasum -a 256 -c SHA256SUMS`），并核对 `lineage-dtbo.json` 中的机型、发布日期、大小和官方摘要。镜像组装时解析当时最新的官方版本；不要在刷写时擅自换成没经过本次配对检查的 DTBO。
3. 在 Fastboot 确认 `product=umi`、已解锁且目标唯一。比较 `boot`、`userdata` 和 `dtbo` 的分区容量与镜像大小。将 `SERIAL` 设为目标的 Fastboot 序列号。

```bash
fastboot -s "$SERIAL" getvar product
fastboot -s "$SERIAL" getvar unlocked
fastboot -s "$SERIAL" getvar partition-size:dtbo
fastboot -s "$SERIAL" getvar partition-size:boot
fastboot -s "$SERIAL" getvar partition-size:userdata
wc -c boot.img rootfs.img
```

## 写入并启动（无需 RAM 探针）

- **已确认现有 DTBO 相容**：保留 `dtbo`，只写下面的 `userdata` 和 `boot`。旧的 `stock-dtbo.txt` 路径仍需核对已安装的摘要和活动索引。
- **DTBO 缺失，或维护者明确授权用官方 DTBO 建立已知基线**：先核对随镜像附带的 `dtbo.img` 容量和摘要，然后执行 `fastboot -s "$SERIAL" flash dtbo dtbo.img`。只有明确成功才继续。此路径不需要事先读活动索引，因为构建时已校验了表的全部条目。
- **Fastboot 不支持读回**不等于 DTBO 缺失；若无法确认当前 DTBO 又未获准覆盖，不要猜测或继续刷写。不要刷 LineageOS 的 `boot.img`、`recovery.img` 或 `vbmeta.img`。

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
