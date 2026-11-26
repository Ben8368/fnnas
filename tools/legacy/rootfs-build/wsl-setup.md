# 在 Windows 上用 WSL2 构建（推荐）

> `tools/legacy/rootfs-build/` 需要 Linux 环境（要 `chroot`、`mount`、`sudo`）。Windows 上最省事的做法是 WSL2。

## 一、装 WSL2

```powershell
# 管理员 PowerShell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
```

**把发行版装到非系统盘**（构建要 50 GB+ 可用空间，建议别放 C 盘）：

```powershell
wsl --export Ubuntu-24.04 D:\wsl\ubuntu.tar
wsl --unregister Ubuntu-24.04
wsl --import Ubuntu-22.04 D:\wsl\Ubuntu D:\wsl\ubuntu.tar --version 2
```

内存 / CPU 限制（可选）—— `C:\Users\<你>\.wslconfig`：

```ini
[wsl2]
memory=8GB
processors=8
```

## 二、装构建依赖

```bash
sudo apt update
sudo apt install -y git gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu build-essential \
    bc bison flex libssl-dev libelf-dev dwarves device-tree-compiler \
    mkbootimg cpio initramfs-tools kmod pigz qemu-user-static e2fsprogs dpkg-dev zstd
```

使用 WSL 内的 Linux 文件系统存放内核工作目录和 rootfs 解包目录。脚本和压缩输入可以从 `/mnt/c` 或 `/mnt/d` 读取。x86-64 构建主机还需要启用 `qemu-aarch64` 的 binfmt 注册。

## 三、构建

从[构建说明](BUILD.md)取得原版 boot 和 rootfs tarball，在本仓库根目录执行：

```bash
CSOT_REFRESH=60 bash tools/legacy/rootfs-build/build-in-wsl.sh /path/to/main-boot.img \
    /path/to/main-rootfs.tar.gz "$HOME/umi-csot-60"
```

配套 boot 和 rootfs 位于 `~/umi-csot-60/assembly/images/`。构建 90 Hz 时设 `CSOT_REFRESH=90` 并使用新的工作目录。显示源码已随仓库提供，构建无需访问外部显示仓库。

## 四、长构建建议放后台

可把内核编译放后台。编译完成后运行[组装命令](BUILD.md)，传入同一个内核工作目录。

```bash
CSOT_REFRESH=90 nohup bash tools/legacy/rootfs-build/build-release-kernel.sh /path/to/main-boot.img \
    "$HOME/umi-kernel-90" > "$HOME/build-run.log" 2>&1 &
tail -f ~/build-run.log
```
