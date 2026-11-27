# 小米 10 原生 fnOS 真机验收

`native` 用已晋升的内核，`native-debug` / `native-acceptance` 用已授权且精确锁定的 CI 候选。默认完整包都含 `dtbo.img`、`boot.img`、`rootfs.img`、`lineage-dtbo.json` 和 `SHA256SUMS`。`boot.img`、`rootfs.img` 绑定同一个根 UUID。构建时从 LineageOS 官方 Umi 发布源解析当时最新的 DTBO、验证大小与官方 SHA-256，并用本次装配的 DTB 保护性检查全部 overlay；任一步失败都不出包。构建和 CI 不写真机。

## 安装前

1. 确认为已解锁的小米 10（Umi）CSOT，已有该机的恢复方案和必要备份。**本次必须明确授权覆盖 `dtbo`、`userdata`、`boot`；写入 `userdata` 会覆盖原系统与数据。**
2. Linux 用 `sha256sum -c SHA256SUMS`，macOS 用 `shasum -a 256 -c SHA256SUMS`，Windows 用 `Get-FileHash -Algorithm SHA256` 逐项比对。核对 `lineage-dtbo.json` 的机型、发布日期、大小和官方摘要。不要在刷机时换用未通过本包校验的 DTBO。
3. 用 `fastboot devices` 确认目标唯一，将 `SERIAL` 设为目标序列号。确认 `product=umi`、设备已解锁，核对 `dtbo`、`userdata`、`boot` 的分区容量与镜像大小（Linux/macOS `wc -c dtbo.img boot.img rootfs.img`；Windows `Get-Item` 的 `Length`）。如果设备公布了下载上限，记录它；若需要稀疏分片，按该上限选择受支持的 `fastboot -S` 大小，不按固定分片数验收。

```bash
fastboot -s "$SERIAL" getvar product
fastboot -s "$SERIAL" getvar unlocked
fastboot -s "$SERIAL" getvar partition-size:dtbo
fastboot -s "$SERIAL" getvar partition-size:userdata
fastboot -s "$SERIAL" getvar partition-size:boot
fastboot -s "$SERIAL" getvar max-download-size
```

## 写入并启动（不做 RAM 探针）

完整包的默认安装顺序为 `dtbo → userdata → boot → reboot`，每一步完整成功后才继续。安装使用**随包 DTBO**，不以读回旧 DTBO、旧摘要或旧活动索引为前置条件。不要刷 LineageOS 的 `boot.img`、`recovery.img` 或 `vbmeta.img`。没有覆盖授权就不执行这条流程；不支持读回也不等于 DTBO 缺失。

```bash
fastboot -s "$SERIAL" flash dtbo dtbo.img &&
  fastboot -s "$SERIAL" flash userdata rootfs.img &&
  fastboot -s "$SERIAL" flash boot boot.img &&
  fastboot -s "$SERIAL" reboot
```

PowerShell 可逐步执行相同命令（用 `$serial` 保存序列号）；每次检查 `$LASTEXITCODE`、全部分片的写入结果和 Fastboot 日志，任何失败立即停止。记录目标序列号、前置检查、各分区摘要、各分片写入结果及重启结果。旧的显式读回调试包只有 `stock-dtbo.txt`，不是默认完整包；仅在另行核对同机已安装摘要与活动索引后保留现有 DTBO，跳过写 `dtbo` 的步骤。RAM 探针保留给需要它的独立诊断。

## 验收 fnOS

- **首启与 USB。** 电脑应同时发现 NCM 网卡和 ACM 串口。串口不用输入即可捕获完整 `UMI_BOOTLOG/1` 摘要，不应有 getty 或 shell。记录内核、根文件系统、DTBO 活动索引及 USB 地址。摘要中的 `dtbo_sha256=unavailable` 表示运行时未取得读回摘要；单独保留已验证的随包摘要和 Fastboot 写入证据，不冒充读回，也不把该值当成串口失效。USB DHCP 应分配 `172.16.42.2/24`，不下发默认网关或 DNS。在 <http://172.16.42.1:5666> 创建管理员账号并登录。仅 DHCP 失败时，在已识别的 USB 网卡上临时手配地址并单独记录。
- **日志与存储。** 如果容量异常或出现报错，先不要重启、初始化、扩容或改分区。网页登录后的事件日志和 USB 摘要都不能代替内核与系统 journal。用管理员会话（例如本地 USB 网络上的 SSH）运行 `sudo bash collect-boot-evidence.sh`，将输出保存在电脑端；保留 boot ID、设备时间和单调启动时间。对照块设备与分区容量、SCSI LUN、根挂载、Btrfs 实际容量和向导候选；匹配型号不能证明小容量设备可安全用作数据盘。只在获准使用、已核对节点的独立测试盘上做读写。原始日志留在本地，外发前审查并脱敏。
- **重启与恢复。** 从已安装的 fnOS 请求进入 Fastboot，确认目标设备成功枚举，再重启回同一套 fnOS 并复查登录和存储。保留启动日志、镜像摘要及 CI Run ID、Attempt、源提交和 Linux 提交。分别记录内核、fnOS 用户态和 OTA 的实际验收结果。
