# 构建 umi 的 Linux / fnOS 底层镜像

> 目标产物：**无桌面、带 Docker、GPU 已启用、电池已启用、CSOT 原生显示**的 Debian/Armbian 底层镜像（供后续 fnOS 用户态适配）
> 目标内核：**Linux 6.18.60 LTS**（上游 Commit SHA：`f45ed76d6791cf72ff1265ee93511175bbbc2f18`，仓库：`https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git`）

官方底包审计与原生 fnOS 组装规划见[构建入口](../../../make-fnos/README.md)。

## 保留 `main` 发布版能力的整镜像重建（推荐用于换内核）

首次构建新 Debian 根文件系统与复现 `main` 成品是两条不同路径。下面的命令以
`main` 引用的 `misaka-link/umi-linux v2026-09-27` 为对照：重编 ARM64 内核和全部模块、
重组 initramfs、重新生成独立 DTB 的 ABL v2 boot 和 ext4 rootfs。经校验的 Debian 13
用户态、固件和已安装的服务作为输入保留，不从 APT 重装整套用户态，也不包含 fnOS 专有用户态。
这是为了保留普通 Armbian DTS/overlay 中没有的 ABL 锚点、GPU 扩展 OPP、Venus 调频和恢复流程。

从该 Release 下载 `boot-umi-csot-ovf-wifi6-gpu-oc-final.img` 与
`umi-system-opensource-2026-09-27.tar.gz`。如已把这两个输入存到本地缓存，运行完整构建时可设 `UMI_BASE_INPUT_DIR=/path/to/cache`；文件名须与上面一致，构建会照常核对固定 SHA-256。在 Ubuntu 24.04 的原生 Linux 文件系统（WSL 时不要用 `/mnt/d` 作工作目录）运行：

```bash
sudo apt install git gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu libc6-dev-arm64-cross build-essential \
    bc bison flex libssl-dev libelf-dev dwarves device-tree-compiler \
    mkbootimg cpio initramfs-tools kmod pigz qemu-user-static e2fsprogs dpkg-dev zstd btrfs-progs rsync

export CSOT_REFRESH=60       # 或 90；每档使用独立的新工作目录
UMI_KERNEL_VERSION=locked ./rekernel-umi /path/to/main-boot.img "$HOME/umi-kernel-61860"
sudo unshare --mount --propagation private bash tools/legacy/rootfs-build/assemble-release.sh /path/to/main-boot.img /path/to/main-rootfs.tar.gz \
    "$HOME/umi-kernel-61860" /var/tmp/umi-image-61860
```

`assemble-release.sh` 需要能运行 ARM64 的 chroot（x86-64 构建机需要启用
`qemu-aarch64` 的 binfmt 注册）。两个工作目录都必须是尚不存在的路径。使用
`JOBS=<并行数>` 调整编译并行度。

输出 `images/boot-umi-csot-60hz-6.18.60.img` 与 `images/rootfs-umi-csot-60hz-6.18.60.img`（90 Hz 时文件名为 `90hz`）。**同次构建配套使用**，root UUID 和模块必须匹配。60/90 是两个固定构建档位。显示源码快照和基线内核配置已纳入仓库，构建会核对基线配置与锁定 boot 输入一致。Btrfs 与 PM8150B 充电器依赖的 ADC5 都编入内核。initramfs 使用经校验 rootfs 中的 `qcom/sm8250/a650_zap.mbn`，覆盖 boot 基线中内容不同的同名固件。

发行版保留 Wi-Fi、GPU、Venus 的板级设置并接入原生显示和 ABL overlay 隔离。由于基线 ADSP 未启用，发行版同时停用依赖其时钟的板载音频节点。FTS 触屏尚未接入驱动，其专用 I2C 控制器也保持停用。

WSL 也可一步执行 `CSOT_REFRESH=90 bash tools/legacy/rootfs-build/build-in-wsl.sh MAIN_BOOT MAIN_ROOTFS_TAR NEW_WORK_DIR`。已知本机原厂 DTBO 表和实际索引时，末尾追加 `ANDROID_DTBO_TABLE INDEX`；会检查 overlay 可应用，且隔离节点外的树不变。不读取或写入手机，不包含原厂 DTBO。见[无刷写验收](../../../docs/04-真机无刷写验收.md)。

---

## GitHub Actions 验证范围

`ci.yml` 在 PR 和推送到 `main` 时运行提交格式、跨平台 ABL 工具、Linux DTB、串口、
限充以及合成底包审计和提取测试。

`build-kernel.yml` 在推送到 `main` 时构建默认 60 Hz 内核，也支持手动选择
`release`、`csot-60`、`csot-90`、`lab-60` 和 `lab-90`。
手动打开 `with_debian_baseline` 后，发布档位还会拉取固定 Debian 归档，重建并校验
配套 Boot 与 ext4 镜像。构建日志和验证信息用 Actions artifact 保存 7 天。

`build-fnos.yml` 的官方底包流程见 [fnOS 构建说明](../../../make-fnos/README.md)。

## CSOT 实验内核与跨环境构建

默认发布仅复用显示；有线 PD/PPS、NFC 等移植见 [CSOT 实验配置](../../../make-fnos/kernel/config/csot/README.md)。
Linux x86-64 使用主机 `cc` 运行保护测试，另用 `aarch64-linux-gnu-gcc` 编译目标；不要把目标编译器设为主机 `CC`。
Windows 通过 WSL2 的 Linux 文件系统构建；源码输入可从 `/mnt/c` 读取，但内核工作目录和输出放 `~/`。保持 Shell 文件为 LF。
macOS/Colima 用 Linux 来宾的原生卷，不把 macOS 共享目录当内核对象目录。先核对来宾架构和工具链；本仓库未验证 Colima 的 fnOS 产物。
若构建报告 future timestamp 或时钟倒退，用宿主单调时钟对照来宾连续采样，并检查 `adjtimex --print` 的频率校正；停用 NTP 不代表已有校频消失，不要靠 `touch` 或禁用检查掩盖偏差。
记录精确 Linux、Armbian 和显示源码 SHA、基线配置 SHA、编译器、最终 `.config` 与 Image/DTB 哈希；主机合成测试、交叉编译和真机结果分开记。

**以下 Armbian 笔记是历史基线，不是原生显示镜像的构建入口。**

## 一、前置条件

| 项 | 要求 |
|---|---|
| 构建主机 | **Linux**（Ubuntu 22.04 / 24.04 推荐）。Windows 可用 **WSL2** |
| 磁盘 | ≥ 50 GB 可用（源码 + 工具链 + 输出） |
| 内存 | ≥ 8 GB（4 GB 会很慢） |
| 网络 | 能访问 github.com / kernel.org / debian 源 |
| 权限 | 需要 `sudo`（构建过程中要 mount / chroot） |

> WSL2 上注意：源码**不要**放在 `/mnt/c/` 下（跨文件系统极慢，且 chroot 会出问题）。
> 放在 WSL 自己的文件系统里，比如 `~/build`。
>
> **WSL2 环境的创建步骤见 [wsl-setup.md](wsl-setup.md)**（磁盘固定在 `E:\WSL2`）。

---

## 二、准备 armbian/build

```bash
sudo apt update
sudo apt install -y git

cd ~
git clone --depth 1 https://github.com/armbian/build.git
cd build
```

先确认 sm8250 family 的 current 内核版本（本移植按 6.18 验证）：

```bash
grep -A2 'current)' config/sources/families/sm8250.conf
# 期望看到 KERNEL_MAJOR_MINOR="6.18"
```

如果不是 6.18，请换用支持此 family 的 Armbian checkout。板级配置在 family 初始化后把
`BRANCH=current` 的检出锁到指定提交；不要通过 `BRANCH=edge` 绕过该锁定。

---

## 三、应用 umi 移植

把本目录（`armbian-umi-port/`）拷到构建机上，然后：

```bash
cd ~/build
~/armbian-umi-port/apply-umi-port.sh ~/build
```

脚本会做四件事：

1. 装 `config/boards/xiaomi-umi.conf`（板级配置）
2. 装三个设备树到 `patch/kernel/archive/sm8250-6.18/dt/`
3. 装 `packages/bsp/xiaomi-umi/zz-update-abl-kernel`
4. 校验依赖的充电补丁是否都在

> **为什么放 `dt/` 就够了**：Armbian 的 `0000.patching_config.yaml` 里有
> ```yaml
> dts-directories:
>   - { source: "dt", target: "arch/arm64/boot/dts/qcom" }
> auto-patch-dt-makefile:
>   - { directory: "arch/arm64/boot/dts/qcom", config-var: "CONFIG_ARCH_QCOM" }
> ```
> 放在 `dt/` 里的 .dts/.dtsi 会被自动复制进内核源码树，Makefile 也会被自动打补丁，
> **不需要手写 Makefile 补丁**。

---

## 四、构建

```bash
cd ~/build

./compile.sh build \
    BOARD=xiaomi-umi \
    BRANCH=current \
    RELEASE=trixie \
    BUILD_MINIMAL=yes \
    BUILD_DESKTOP=no \
    KERNEL_CONFIGURE=no \
    ENABLE_EXTENSIONS="docker-ce umi-usb-host umi-kernel-tweaks" \
    EXPERT=yes
```

参数说明：

| 参数 | 作用 |
|---|---|
| `BRANCH=current` | 用 sm8250 family 的 current 分支 = **6.18 LTS**（此板固定在 6.18.60） |
| `RELEASE=trixie` | Debian 13。要 Ubuntu 24.04 就换 `noble` |
| `BUILD_MINIMAL=yes` | **纯 CLI，不装桌面** |
| `ENABLE_EXTENSIONS="docker-ce …"` | 三个扩展，见下表 |
| `KERNEL_CONFIGURE=no` | 不弹内核配置菜单 |

**三个扩展分别做什么：**

| 扩展 | 作用 |
|---|---|
| `docker-ce` | Armbian 官方扩展：构建时从 Docker 官方源装好 `docker-ce` / `containerd.io` / `docker-compose-plugin` |
| `umi-usb-host` | 打开 USB host 所需内核选项（关键是 `CONFIG_USB_ROLE_SWITCH`）→ 键鼠可用 |
| `umi-kernel-tweaks` | 把 apparmor 加进 `CONFIG_LSM`（让已编译的 AppArmor 真正生效）+ 服务器向内核选项 |

> 也可以把这一长串存成 `userpatches/config-umi.conf`，之后 `./compile.sh umi` 即可。

首次构建约 **1–2 小时**（要下载工具链、编内核）。
重复构建会走 ccache，快很多。想强制干净重建加 `CLEAN_LEVEL=make-kernel`。

**产物**在 `output/images/`，会长这样：

```
Armbian_<版本>_Xiaomi-umi_trixie_current_6.18.x_minimal.rootfs.img
Armbian_<版本>_Xiaomi-umi_trixie_current_6.18.x_minimal.boot_sm8250-xiaomi-umi-csot.img
Armbian_<版本>_Xiaomi-umi_trixie_current_6.18.x_minimal.boot_sm8250-xiaomi-umi-sms.img
```

- `*.boot_<dtb>.img` → 刷到手机的 **`boot`** 分区
- `*.rootfs.img` → 刷到给 Linux 用的分区（不要安卓的话，直接刷 `userdata`）

---

## 五、刷机

**前置：Bootloader 已解锁**（小米10 需要社区等级/答题，或走 `Xiaomi-HyperOS-BootLoader-Bypass`）。

⚠️ **先确认你的面板型号**（决定用哪个 boot 镜像）：

```bash
# 方法一：从设备树读（需 root）
adb shell su -c 'cat /sys/firmware/devicetree/base/model'
# 方法二：拨号 *#*#6484#*#* 进 CIT → LCM Information 看厂商前缀
```

本机已知是 **CSOT（华星光电）**，所以用 `..._boot_sm8250-xiaomi-umi-csot.img`。

```bash
adb reboot bootloader

# 刷 boot
fastboot flash boot Armbian_..._minimal.boot_sm8250-xiaomi-umi-csot.img

# 刷 rootfs（不要安卓 → 直接刷 userdata；想保留安卓就换成别的空闲分区）
fastboot flash userdata Armbian_..._minimal.rootfs.img

fastboot reboot
```

> **如果 umi 是 A/B 双槽**（先跑 `fastboot getvar current-slot` 确认），
> 那么分区名可能是 `boot_a`/`boot_b`，用 `fastboot flash boot_a ...`。
> A/B 设备还能做到"安卓留在 A 槽、Linux 住 B 槽"。

---

## 六、镜像开箱即有的东西

构建出来的镜像**默认**已经是这样（不需要你手动配）：

| 项 | 默认值 | 由谁设置 |
|---|---|---|
| **SSH** | 初始关闭，手动启用后仅普通账号公钥登录 | `customize-image.sh` |
| **root 密码** | 初始锁定，首次连接 USB 串口时设置 | `umi-serial-console` |
| **普通管理员** | 由机主在串口创建 | `adduser` / `sudo` |
| **启动目标** | `multi-user.target`（纯 CLI） | `customize-image.sh` |
| **息屏** | `consoleblank=60` | 板级配置的 cmdline |
| **USB 键鼠** | 插 OTG 转接头即用 | 设备树 + `umi-usb-host` 扩展 |
| **USB 网卡和串口** | NCM 网卡（设备端 `172.16.42.1`）与 ACM 串口 | 设备树 + `umi-usb-gadget.service` |
| **Docker** | 已安装 | `docker-ce` 扩展 |
| **常用工具** | htop / tmux / v4l-utils / i2c-tools / dtc / usbutils 等 | `customize-image.sh` |
| **休眠挂起** | 已 mask | `customize-image.sh` |
| **上手说明** | `/root/README-mi10.md` | `customize-image.sh` |

登录流程见下一节。使用继承的 `v2026-09-27` 镜像时，按 [旧基线的账号与密码说明](../../../docs/01-快速开始.md#31-先说清楚这个镜像里有哪些账号)操作。

---

## 七、首次开机后必做

### 设置本机密码和 SSH

1. 用支持数据传输的 USB 线连接电脑。Windows 打开设备管理器里的 `COMx`，Linux 打开 `/dev/ttyACM0`。串口参数为 `115200 8N1`，关闭流控。按回车，按提示设置本机独立的 root 密码，再用该密码登录串口。设密前拔线或按 `Ctrl+C` 后，可以重连再试。
2. 如需 SSH，在串口以 root 创建自己的普通管理员。把下面的 `umiadmin` 改成你要用的账号名。

   ```bash
   adduser umiadmin
   usermod -aG sudo umiadmin
   install -d -m 700 -o umiadmin -g umiadmin /home/umiadmin/.ssh
   ```

3. 在串口将电脑上现有的 SSH **公钥**（例如 `~/.ssh/id_ed25519.pub` 文件中的一整行）写入 `/home/umiadmin/.ssh/authorized_keys`，然后执行以下命令。

   ```bash
   chown umiadmin:umiadmin /home/umiadmin/.ssh/authorized_keys
   chmod 600 /home/umiadmin/.ssh/authorized_keys
   ssh-keygen -A
   install -d -m 0755 /run/sshd
   /usr/sbin/sshd -t
   systemctl unmask ssh.service
   systemctl enable --now ssh.service
   ```

4. 保持串口打开，从电脑执行 `ssh umiadmin@172.16.42.1`。在 SSH 会话中执行 `sudo -v` 确认管理员权限。如果电脑没拿到地址，给 USB 网卡设置 `172.16.42.2/16`。串口上的 root 密码可以用 `passwd root` 修改。

### 系统设置

```bash
# 1) 整盘扩容（rootfs 镜像是按最小尺寸生成的，Docker 会撑爆）
sudo resize2fs $(findmnt -no SOURCE /)
df -h /

# 2) 确认息屏生效（AMOLED 黑屏 = 像素不发光）
cat /sys/class/graphics/fb0/blank      # 期望 4
# 想立刻手动黑屏：echo 4 | sudo tee /sys/class/graphics/fb0/blank

# 3) 联网（USB 线插上就是网卡，systemd 服务默认已启用）
ip -br link
# WiFi 备用：
nmcli device wifi list && nmcli device wifi connect "<SSID>" password "<密码>"
```

---

## 八、验收清单

构建前可运行 `bash tools/legacy/rootfs-build/tests/test-serial-enrollment.sh` 检查设密状态切换，不会修改运行测试的电脑密码。

先用新刷写的测试镜像验收登录流程。设密前应能发现 USB 串口且 SSH 不接受连接；中断一次设密后重连应仍能进入设密。设密完成后退出再连、重启再连，都应要求密码。启用 SSH 后，用管理员公钥登录并验证 `sudo -v`，同时确认 root 和密码认证会被拒绝。检查有效配置时使用 `sudo /usr/sbin/sshd -T`，确认 `permitrootlogin no`、`passwordauthentication no`、`kbdinteractiveauthentication no` 和 `authenticationmethods publickey`。

```bash
# --- GPU ---
ls -l /dev/dri/                        # 期望出现 renderD128
dmesg | grep -i -E "adreno|msm|zap"    # 不应有 "failed to load zap shader"

# --- 电池 ---
ls /sys/class/power_supply/            # 期望有 BAT0 / AC / USB
cat /sys/class/power_supply/*/capacity 2>/dev/null
cat /sys/class/power_supply/*/status

# --- 视频编解码 (Venus) ---
dmesg | grep -i venus
v4l2-ctl --list-devices
ffmpeg -hwaccel v4l2m2m -c:v h264_v4l2m2m -i test.mp4 -f null -

# --- WiFi ---
lspci -nn | grep -i qualcomm
dmesg | grep -i ath11k

# --- Docker ---
docker version
docker run --rm --device /dev/dri hello-world
```

---

## 九、故障排查

### 开不了机 / 卡在启动
刷回之前备份的 boot 镜像即可（`fastboot flash boot boot-backup.img`）。
**刷之前一定要先备份**：
```bash
adb shell su -c 'dd if=/dev/block/by-name/boot of=/sdcard/boot-backup.img'
adb pull /sdcard/boot-backup.img
```

### 电池相关的节点导致编译失败
如果 `&pm8150b_charger` / `&pm8150b_fg` 报 "undefined label"，说明当前补丁集里
没有 0027/0029 那两个补丁。检查：
```bash
ls patch/kernel/archive/sm8250-6.18/ | grep -E "0027|0029|0037"
```
缺哪个就去 `patch/kernel/archive/sm8250-6.19/` 或 6.12 目录里找同名文件补上。

### 构建失败在 `config/boards/xiaomi-umi.conf` 某一行
最常见的是板级配置里引用了**已过时的 Armbian 内部文件名**。已知坑：

| 旧写法（会失败） | 现代写法 |
|---|---|
| `/etc/apt/sources.list.d/armbian.list` | **`/etc/apt/sources.list.d/armbian.sources`** |

Armbian 只在 `SKIP_ARMBIAN_REPO=yes` 时把 `armbian.sources` 改名成 `armbian.sources.disabled`，
所以**不能无条件 `mv`** —— 要加 `[ -e ]` 守卫，否则文件不存在时 `set -e` 直接中断构建。

本移植包已经按现代写法改好了。如果你从别处抄板级配置，**先对照官方同平台板级配置核实**
（`config/boards/xiaomi-elish.conf` 是最好的参照，它一直在维护）。

### 某个包安装失败导致整个构建挂掉
板级配置里 `chroot_sdcard_apt_get_install` 一次装多个包时，只要有一个在目标 release 里不存在就会整体失败。
本移植包改成了**逐个安装 + 失败告警跳过**：

```bash
for pkg in qbootctl qrtr-tools unudhcpd mkbootimg device-tree-compiler ; do
	do_with_retries 2 chroot_sdcard_apt_get_install "$pkg" \
		|| display_alert "Skipping package" "${pkg} 安装失败，继续" "warn"
done
```

### 电量显示不出来
先确认电量计到底是哪一颗（在现有 MIUI 上跑）：
```bash
adb shell ls /sys/bus/i2c/devices/
adb shell cat /sys/class/power_supply/*/name
```
如果显示的是 `bq27z561` 之类**外挂**芯片，就照 Armbian 补丁 `0022` 里 elish 的写法，
在对应 i2c 总线上加节点，而不是用 `&pm8150b_fg`。

### GPU 还是没起来
```bash
dmesg | grep -i -E "zap|adreno|gmu"
```
若报 `failed to load zap shader` → 固件缺失。确认：
```bash
ls -l /lib/firmware/qcom/sm8250/a650_zap.mbn /lib/firmware/qcom/a650_gmu.bin
```
没有的话装 `armbian-firmware-full`，或者把 `firmware-name` 改成分片路径
`qcom/sm8250/xiaomi/elish/a650_zap.mbn`（如果装了 Armbian 固件包的话）。

### 内核升级后息屏失效
`zz-update-abl-kernel` 重建 boot 镜像时已带上 `consoleblank=60`。
如果手动改过，检查 `/proc/cmdline` 里有没有 `consoleblank=60`。

---

## 十、这个移植改了什么（对照原始 fork 版本）

| # | 改动 | 原因 |
|---|---|---|
| 1 | GPU `tatus` → `status` | 一个字母的笔误，导致 Adreno 650 静默禁用 |
| 2 | GPU zap shader 路径改为主线通用 `qcom/sm8250/a650_zap.mbn` | 原路径指向 elish 专属目录，依赖 Armbian 固件包 |
| 3 | `battery` 节点取消注释并修正参数 | 原参数（4300mAh/16.6Wh）是从小米平板5 抄来的 |
| 4 | 新增 `&pm8150b_charger` / `&pm8150b_fg` | 原来只有一行 `//TODO: Port the CHARGER Driver` |
| 5 | 新增 BQ25970 快充节点（默认注释） | 原 DTS 里有注释掉的 `bq25970-standalone`，附上启用说明 |
| 6 | cmdline 加 `consoleblank=60` | 息屏（AMOLED 黑屏等效熄火，防烧屏） |
| 7 | 板级配置：`BOARDFAMILY="sm8250"`（原来是 `qcom-abl`） | 用官方 family 才能吃到 `qcom_fg` / `pm8150b_charger` 补丁 |
| 8 | 板级配置：加 initrd 固件 hook | 保证 GPU / Venus 固件早期可加载 |
| 9 | `zz-update-abl-kernel`：cmdline 补 `consoleblank=60` | 原版硬编码 cmdline，内核升级后息屏设置会丢 |
| 10 | `zz-update-abl-kernel`：面板探测失败时报错而非静默默认 csot | 避免打错 DTB |
| 11 | 设备树：新增 USB OTG（`pm8150b_typec` + connector + `pm8150b_vbus` + dwc3 端点） | 让 USB 口能切 host 模式接键鼠（照抄补丁 0038 的 oneplus 实现） |
| 12 | 设备树：`&usb_1_dwc3` 补 `role-switch-default-mode = "peripheral"` | 默认提供 USB gadget，插外设自动切 host |
| 13 | 扩展 `umi-usb-host.sh`：打开 `CONFIG_USB_ROLE_SWITCH` 等 | **defconfig 里没有这一项，不开的话 `usb-role-switch` 属性完全无效** |
| 14 | `umi-usb-gadget.service` 与 `umi-serial-console` | 使用 USB 串口首次设密，之后通过密码登录串口 |
| 15 | `customize-image.sh`：擦除继承的 root 密码和 SSH 主机密钥，安装工具 | 机主添加普通管理员公钥后自行开启 SSH |
| 16 | `customize-image.sh`：`systemctl mask sleep/suspend/hibernate` | 服务器不该睡 |

---

## 十一、测试与「不重建就改镜像」

### 11.1 单测

`tests/test-charge-limit.sh` —— 限充脚本的滞回逻辑回归测试，**纯 bash，与架构无关**，
在 x86 的 WSL 里也能直接跑：

```bash
bash tests/test-charge-limit.sh
# 或指定被测脚本
bash tests/test-charge-limit.sh /usr/local/bin/battery-charge-limit
```

三层覆盖：

| 层 | 测什么 | 数量 |
|---|---|---|
| A | `decide()` 纯函数穷举：电量 × 状态 的组合，断言「动作 + 新状态」 | 20 |
| B | 端到端：造假 sysfs 树（`BAT0/capacity` + `pm8150b_charger/charging_enabled`），真跑脚本，断言写入序列 | 10 |
| C | 配置校验（非法 `UPPER` 拒绝启动、`UPPER<=LOWER` 告警）与内核原生 `charge_control_end_threshold` 分支 | 7 |

B 层用了一个小技巧来区分「没写」和「重复写了同样的值」：
`charging_enabled` 是普通文件，脚本每次真正写入都会刷新 mtime，
所以断言「值不变 **且** mtime 不变」才能证明中间区间确实没动手。

脚本为可测性做了两处设计（生产行为不变）：
- `decide()` 把决策从主循环里抽成纯函数
- `BATTERY_CHARGE_LIMIT_LIB=1` 时只加载函数、不碰 `/sys`、不进主循环
- `SYSFS_ROOT` 可覆盖，指向假 sysfs 树

### 11.2 只改一个文件时，不必重建整个镜像

改了 overlay 里的脚本后，重跑一次完整构建要重新 clone Armbian + 编译内核 + 打 rootfs，
代价很大。而 rootfs 就是一个普通 ext4 镜像，可以直接挂载替换文件：

```bash
sudo bash tests/patch-rootfs-charge-limit.sh
```

它会：只读挂载确认现状 → 可写挂载替换 → **就地跑单测**（单测不过就中止，不把坏东西留下）
→ 核对 systemd 单元与 `/etc/default` → 卸载 → 重算 4 个 sha256。

配套的完整性检查：

```bash
sudo bash tests/check-rootfs-integrity.sh
```

跑 `e2fsck -fn`（只读，不改）+ `sha256sum -c` + 确认关键文件在位。

> 注意：这两个脚本是给 **WSL/Linux 上的 root** 用的。脚本支持环境变量覆盖路径：
> `OUT=<镜像目录> IMG=<rootfs.img> bash check-rootfs-integrity.sh`。
> 镜像文件名变了要同步改 `IMG=`。
