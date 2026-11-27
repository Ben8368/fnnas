# Umi ARM64 的 trimafs 兼容性与真机挂载验证

官方 ARM64 1253 镜像归档 SHA-256 为 `0453f9b98cf1cdc8b710fc7f1b040c73160d10d5f66b131cfaf722226c877066`。其 `6.18.18-trim` 的 System.map 含 `init_trimafs_fs` 的内建 initcall 和权限、目录、ACL 路径；没有在此供体中找到可复制到新内核的 trimafs 模块。`triminit` 执行不带选项的 `mount -t trimafs trimafs /fs`。这里验证的是社区重写能否兼容这条路径，**不是**获得了飞牛官方 ARM64 补丁。

## 精确输入和构建边界

| 输入 | 版本或 SHA |
| --- | --- |
| Umi 配置及预打补丁 Linux 树的项目版本 | `0a598a368247a7b70368df8d7722ad433eba1fdb`，`csot-90` |
| 实验前向 Linux Stable 重新查询的最高正式 6.18.y | `v6.18.65`，`4700e3adf3b24b39dd4929e9c6d62811ba3ccea8` |
| 社区实现 | [CharlesGool/fnOS-cust-kernel 固定提交](https://github.com/CharlesGool/fnOS-cust-kernel/tree/6e24d88179117e46c78ce3023b793f3f2b93b444)，按其 `patches/kernel/series` 原序使用 110 个补丁，没有跳过 |
| 本地后置修正 | `../sources/trimafs-vm-arm64.patch`，SHA-256 `8a4588fcb4607181ec1cf44c7a0fc1a981268a8ec4feaf37f9038105623fb542` |
| QEMU 用户态 | 上一版 Umi 原生 Btrfs `rootfs.img`，SHA-256 `fbabd1484df1773e0d9871380cd2a4734dd631ecf087aeb7c8e3d962f62a9715` |
| 实验 ARM64 `Image`（非 `boot.img`，无配套模块包） | SHA-256 `2b24d650f64a0a0a9c2a3a183c4a5457de650c2d29f0c6974e85c9c37a14b761` |

复现只在**私有临时 Linux 源码副本**：从 Umi 预打补丁树和其最终 `.config` 开始；从上述社区 Git 提交用 `git archive` 取出原始 LF 字节（不是 Windows 自动转 CRLF 后的补丁），依次 `git apply`，首个失败即停止。应用本地后置修正，保留所有原作者声明；启用 `EXPORTFS`、`FS_TRIM_ACL`、`TRIMAFS2_FS`，`ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-` 下 `olddefconfig` 后编译 `Image`。此流程**未接到** `rekernel`、正式镜像组装或发布。社区全系列还改动 Btrfs、MD RAID、NFS、VFS 等；不能把这份 `Image` 与原 Umi 模块或 ZFS 包混用。正式集成需审计补丁/许可证与对外模块 ABI，针对同一内核重新编译并验收，不能仅按注册名或同一版本号替换文件。

## 为什么“挂载成功”还不够

1. 社区原版在 ARM64 编译 `fs/trim_acl.c` 时，`try_cmpxchg` 的期望值类型不匹配。局部修正将哨兵改成与缓存槽匹配的指针，只保留原哨兵值，不禁用编译器检查。
2. 仅修编译时，未带选项的 `mount` 成功、桥接和文件读写也成功，但对 UID 2002 显式配置 deny 后，该用户仍可经 `/fs` 读取 0644 文件；此版本**不可用**。启用聚合挂载的 `trimacl` 选项后同一测试能拒绝访问。最终修正将实验内核中的默认值改为开启，因而不需要改写飞牛 `triminit`、不需要覆盖系统 `mount` 命令。
3. 最终 QEMU 试验：镜像自带的 `/usr/trim/bin/trimacl` 在 162.28 GiB 仿真第 35 分区的 Btrfs（`-o trimacl`）中写入规则。根用户按飞牛方式通过绝对路径 symlink 创建目录桥。UID 2001 可读；UID 2002 从下层及桥均不可读，也不能擅自创建桥。卸载并重新挂载两个文件系统、重建桥后，原数据和 allow/deny 仍正确。仅验证上述卷类型、路径和身份，不等于所有权限语义、全部共享协议、真机重启、Web 建卷或 OTA 通过。

单纯 bind mount、软链接替代整个 `/fs`，或在启动脚本里吞掉挂载错误，都不能交付上述权限语义。创建用户存储的边界及原厂 GPT 特性见 [Umi 存储布局](umi-storage-layout.md)。

## 2026-11-27 小米 10 真机挂载

在上述源码基础上重新编译完整内核和模块，版本为 `6.18.65-csot90-sm8250-trimafs1`。完整模块构建中，社区 RAID 代码以模块形式编译失败。本次使用 `CONFIG_BLK_DEV_MD=y`、`CONFIG_MD_DEGRADATION_FREE_RECOVER=y`，并关闭 `CONFIG_MD_AUTODETECT`；OpenZFS 2.4.1 针对同一个内核重新构建。为适配原 ABL 的加载地址，initramfs 只携带 151 个经字节和 vermagic 核对的模块，启动时通过 tmpfs 提供给已安装用户态。

| 字段 | 完整值 |
| --- | --- |
| 板型与配置 | Xiaomi Mi 10 (Umi)，`csot-90` |
| FnNAS 内核输入基线 | `0a598a368247a7b70368df8d7722ad433eba1fdb` |
| 打包时 FnNAS 工作区 HEAD | `dbddd6fb52caa128fffaa20ad5e386e32c67a66d` |
| Linux Stable | `4700e3adf3b24b39dd4929e9c6d62811ba3ccea8` |
| 社区补丁基线 | `6e24d88179117e46c78ce3023b793f3f2b93b444` |
| 最终内核配置 SHA-256 | `0f34aa194ef9e93818ab37a42a28fa8c54f94a24b7bd0638a9de45f99ca47c91` |
| 本地调试包 SHA-256 | `247d5fe2bddfbacf5966a9ec98839660379ab554dfdecdb8b63f1f2961a515c2` |
| 已刷 boot.img SHA-256 | `f8910069be0ffc0c66a112842b8fcdd7a2338067278c62702a7c469fe6408060` |

已捕获的原厂 DTBO（SHA-256 `47cd75d0f1564355ef85b24ba4b1d1ecfeac3e7a6b11be480685d46c4b9cf4b9`）通过全部 12 项 overlay 预检。Fastboot 于 18:07 CST 确认写入 `boot` 并重启。现有 fnOS 用户态经 Btrfs 根启动，USB ACM 输出以下字段，Web 探测返回 HTTP 200。

```text
kernel=6.18.65-csot90-sm8250-trimafs1
rootfs=btrfs
dtbo_index=11
root_uuid=8357e99b-86e2-4698-be5e-85b06d81b5de
fs_mount=trimafs
trim_init.service=active
trim_nginx.service=active
usersrv.service=active
```

同一最终内核在 ARM64 QEMU 通过无挂载参数的 `trimafs` Btrfs 桥接及 ACL 回归，以及 Btrfs、ext4、OpenZFS 读写和 ZFS 池导出、重新导入验证。构建主机的完整记录位于 `out/umi-persistent-trimafs/`，包括 `build-inputs.txt`、`SHA256SUMS`、`build-kernel.log`、`build-openzfs.log`、`package-audit.log`、`dtbo-preflight.log`、`device-flash.log`、`device-trimafs-frame.txt`、`final-guest.log` 和 `fs-qemu.log`。

本次真机范围为已安装 fnOS 启动和 `/fs` 挂载。Web 建卷、共享与普通用户 ACL、Fastboot 回滚复验、OTA 和内核晋升仍待验收。
