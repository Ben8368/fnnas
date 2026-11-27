# Umi 系统盘与用户存储：64 GiB + 剩余空间

## 2026-11-27 真机只读结果

这台 256 GB Umi 的 WDC `SDINEDK4-256G` 有多个 UFS LUN。`/dev/sda` 是主 LUN 0，容量约 237.28 GiB；`/dev/sde`（1 GiB）和 `/dev/sdf`（64 MiB）分别是同一颗 UFS 的 LUN 4 和 5，不是额外的 NAS 数据盘，不得在向导中选中。`/dev/sda34` 是 GPT 最后一项 `userdata`，根 Btrfs 挂到 `/`，文件系统目前约 8.27 GiB，但外层分区是 226.28 GiB。分区内部的 slack 不是 GPT 未分配空间。

从实际 4096 字节逻辑扇区计算的目标（末扇区包含在范围内）：

| 区域 | 起始 LBA | 最后 LBA | 容量 |
| --- | ---: | ---: | ---: |
| 保留 `/dev/sda1`–`/dev/sda33` | 原值 | 原值 | 不动 |
| fnOS 系统 `/dev/sda34` (`userdata`) | 2,883,584 | 19,660,799 | 64 GiB |
| 留给用户存储的尾部 | 19,660,800 | 62,201,850 | 162.28 GiB（格式化前） |

不要在其他型号、容量或分区版本上照抄扇区。用 `collect-boot-evidence.sh` 获取当前挂载、Btrfs `Device size` 和 `sfdisk --json`，将其中 GPT JSON 提取到本地，再用 `python3 plan-umi-storage.py GPT_JSON --root-device ROOT_NODE --btrfs-device-bytes BYTES` 生成预览。规划器不操作块设备，输出不是分区工具的输入文件。切分后、创建数据卷前，对相同命令加上 `--verify-after AFTER_JSON`，验证 GPT 只有 `userdata` 的长度变化，其他表头和分区均保持一致。

## 离线演练

在有 `losetup`、`sfdisk` 和 `btrfs` 的 Linux 上，可用 `rehearse-umi-storage.py`。脚本在私有临时目录新建稀疏文件，以捕获的 GPT JSON 重建布局并放入经 SHA-256 校验的原生 `rootfs.img`。它只操作自己创建的 loop 设备；不接受真机作为输出。使用实际 `lsblk` 的磁盘字节数，不能把厂商标称容量传给 `--disk-bytes`。

```sh
sudo python3 rehearse-umi-storage.py GPT_JSON --disk-bytes DISK_BYTES \
  --root-device ROOT_NODE --rootfs ROOTFS_IMG --rootfs-sha256 ROOTFS_SHA256
```

2026-11-27 离线演练：真机捕获的 34 项 GPT 在 4 KiB 扇区副本上重建并通过验证；改动仅限 `userdata` 长度，切分后原生 Btrfs 镜像通过 `btrfs check --readonly`，回滚后该副本的主、备 GPT 区域与切分前逐字节一致。此结果不是对真机原始 GPT 的字节备份，也没有验收真机启动、Btrfs 扩容或 fnOS 建卷。

## 后续实施与验收（尚未在真机执行）

1. 保留原始 GPT 的可恢复备份，以及系统、应用配置、用户数据和现有可启动镜像；先在离线副本演练分区及恢复。真机修改需另行授权并从能确认根盘未挂载的维护环境进行。只缩短 `userdata` 的尾端，保留其编号、起点、名称、类型、PARTUUID 和 Btrfs UUID；不改其他分区或 LUN。如果旧 Btrfs 当前超过目标边界，停止，不裁剪块设备。
2. 真机操作后，先确认原根 UUID 可启动、`userdata` 实际只有 64 GiB、分区表前 33 个条目未变；再把 Btrfs 增长到新的分区边界。此时仅使用 64 GiB 的分区增长，不允许自动吞掉整块 UFS。
3. [飞牛官方《如何创建存储空间？》](https://help.fnnas.com/articles/v1/volume/create) 支持用系统盘剩余空间创建独立存储。本移植环境还没有验过这条路径。先把尾部留作 GPT 未分配空间，观察 fnOS 是否给出专用的「系统盘剩余空间」候选。只有明确核对所选范围是上述尾部，且不会重建主盘分区表或清除系统分区，才另行确认建立数据卷；不要选择 1 GiB/64 MiB 项，也不要把整块 `/dev/sda` 当空盘初始化。
4. 创建后验收 Web 文件管理、普通用户权限、写入读回以及 Fastboot 往返后的持久性。当前启动曾出现 `/fs` 挂载的 `unknown filesystem type 'trimafs'`，需要确认是否影响 fnOS 的存储和共享功能。如果向导不识别剩余空间或创建失败，先检查日志；可另评估独立数据分区加常规文件系统和文件共享，不把 Linux 能挂载等同于 fnOS 已接管。

划分后 Fastboot 的 `userdata` 容量会变小。后续安装仍应预检该分区容量；禁止使用会重建整盘 GPT 的刷机方式，否则用户数据分区可能丢失。

## 用原厂 GPT 字节和飞牛 ARM64 用户态做的补充实验（仅限虚拟磁盘）

在 QEMU 中使用与 Umi 一致的 4096 字节逻辑扇区、34 项分区、原始主备 GPT 元数据副本和已校验的原生 Btrfs 镜像。以第 34 分区为只读根，调用镜像中未修改的 `libndev.so`：`is_sys_disk` 对模拟主盘返回 1，`get_sys_disk_free_space_partno()` 返回 35。客体枚举为 `sdb` 而非手机上的 `sda`；不是把设备名硬编码成系统盘。在一次性快照中单独重放该版本 `storage.hdl` 系统盘分区路径使用的 `parted` 参数，产生了起始 LBA 19,660,800、大小 **174,247,116,800 字节**的 Linux RAID 类型分区。末尾余 251 个逻辑扇区，这是对齐，不是少识别了 160 GiB。没有经过 Web 建卷接口，不能据此认为飞牛已接管新卷。

**不能只看 `sfdisk --verify`。** 上述分区命令成功，原 34 个逻辑分区未变，但逐字节对比发现保护 MBR 也有改动，备份 GPT 表头中的数组起点从 62,201,851 移至 62,201,853。Linux 能正常读新表不代表手机引导链或回滚流程接受它。不要对真机照抄 `parted` 命令。也不能把改表前的备份直接恢复到已有数据卷的设备上。

`prepare-umi-storage-fixture.py` 为这台 **256 GB / 4 KiB** Umi 生成独立的离线实验输入，不是刷机程序。传入 `sfdisk` JSON、之前独立核验的两个**仅元数据**文件及 SHA-256、当时单设备 Btrfs 的设备字节数和一个不存在的输出目录。工具核对主备表的 CRC、原始分区条目、布局和身份，拒绝包含最后一个 userdata 扇区的宽窗口备份。默认只模拟缩短 userdata；可选 `--test-data-guid UUID` 在试验副本中增加一个与飞牛路径编号、类型和容量一致的空条目。两个模式均保留原 PMBR、备份数组位置、厂商分区及填充字节。输出 `*.fixture` **不是通用镜像，不得用 fastboot 刷写**。测试 GUID 不得用于其他设备。

`plan-umi-storage.py` 的 `--verify-after JSON` 用于检查缩尾后的逻辑 GPT；`--verify-created JSON` 专门检查该版系统盘路径新增的单个 RAID 类型分区（验证编号、起始位置、容量、PARTUUID 及其他分区不变）。两者都以切分前的 GPT 和 Btrfs 设备边界为输入；都不替代原始主备元数据对比。预留第 35 项只是避免 `parted` 重排 GPT 的一种待验证方案：仍需证明 fnOS 向导接受它、只格式化该分区、不重建整盘，并在重新启动后保留数据。
