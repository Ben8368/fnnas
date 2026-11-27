# Umi 系统盘与用户存储：64 GiB + 剩余空间

## 2026-11-27 真机只读结果

这台 256 GB Umi 的 WDC `SDINEDK4-256G` 有多个 UFS LUN。`/dev/sda` 是主 LUN 0，容量约 237.28 GiB；`/dev/sde`（1 GiB）和 `/dev/sdf`（64 MiB）分别是同一颗 UFS 的 LUN 4 和 5，不是额外的 NAS 数据盘，不得在向导中选中。`/dev/sda34` 是 GPT 最后一项 `userdata`，根 Btrfs 挂到 `/`，文件系统目前约 8.27 GiB，但外层分区是 226.28 GiB。分区内部的 slack 不是 GPT 未分配空间。

从实际 4096 字节逻辑扇区计算的目标（末扇区包含在范围内）：

| 区域 | 起始 LBA | 最后 LBA | 容量 |
| --- | ---: | ---: | ---: |
| 保留 `/dev/sda1`–`/dev/sda33` | 原值 | 原值 | 不动 |
| fnOS 系统 `/dev/sda34` (`userdata`) | 2,883,584 | 19,660,799 | 64 GiB |
| 留给用户存储的尾部 | 19,660,800 | 62,201,850 | 162.28 GiB（格式化前） |

不要在其他型号、容量或分区版本上照抄扇区。用 `collect-boot-evidence.sh` 获取当前挂载、Btrfs `Device size` 和 `sfdisk --json`，将其中 GPT JSON 提取到本地，再用 `python3 plan-umi-storage.py GPT_JSON --root-device ROOT_NODE --btrfs-device-bytes BYTES` 生成预览。规划器不操作块设备，输出不是分区工具的输入文件。

## 后续实施与验收（尚未在真机执行）

1. 保留原始 GPT 的可恢复备份，以及系统、应用配置、用户数据和现有可启动镜像；先在离线副本演练分区及恢复。真机修改需另行授权并从能确认根盘未挂载的维护环境进行。只缩短 `userdata` 的尾端，保留其编号、起点、名称、类型、PARTUUID 和 Btrfs UUID；不改其他分区或 LUN。如果旧 Btrfs 当前超过目标边界，停止，不裁剪块设备。
2. 真机操作后，先确认原根 UUID 可启动、`userdata` 实际只有 64 GiB、分区表前 33 个条目未变；再把 Btrfs 增长到新的分区边界。此时仅使用 64 GiB 的分区增长，不允许自动吞掉整块 UFS。
3. [飞牛官方《如何创建存储空间？》](https://help.fnnas.com/articles/v1/volume/create) 支持用系统盘剩余空间创建独立存储。本移植环境还没有验过这条路径。先把尾部留作 GPT 未分配空间，观察 fnOS 是否给出专用的「系统盘剩余空间」候选。只有明确核对所选范围是上述尾部，且不会重建主盘分区表或清除系统分区，才另行确认建立数据卷；不要选择 1 GiB/64 MiB 项，也不要把整块 `/dev/sda` 当空盘初始化。
4. 创建后验收 Web 文件管理、普通用户权限、写入读回以及 Fastboot 往返后的持久性。当前启动曾出现 `/fs` 挂载的 `unknown filesystem type 'trimafs'`，需要确认是否影响 fnOS 的存储和共享功能。如果向导不识别剩余空间或创建失败，先检查日志；可另评估独立数据分区加常规文件系统和文件共享，不把 Linux 能挂载等同于 fnOS 已接管。
