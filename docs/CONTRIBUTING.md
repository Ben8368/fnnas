# 贡献指南

先读[项目说明](../README.umi.md)和[许可与出处](../NOTICE.md)。修改 boot、内核或 rootfs 时，按[自行构建](03-自行构建.md)选择对应的构建流程。

## 本地检查

在 Ubuntu 或 WSL 的 Bash 中，从仓库根目录运行同一套 CI 检查。它会检查 Shell 语法、Python 工具、设备树编译、串口设密和充电上限逻辑，无需连接手机或下载完整 rootfs。

```bash
sudo apt-get update
sudo apt-get install -y python3 device-tree-compiler
bash tools/ci-check.sh
```

在 Windows 或 macOS 上可用 `python -B -m unittest discover -v -s make-fnos/boot/abl-android-v2/tests` 单独运行 boot 工具测试。该套件中依赖 DTC 的用例会在未安装 `dtc` 时跳过。rootfs 的 DTB 测试由 Ubuntu CI 运行。

修改官方底包审计时，在装有 `python3-guestfs`、`btrfs-progs` 和可读内核镜像的 Linux 上运行：

```bash
FNOS_PYTHON=/usr/bin/python3 /usr/bin/python3 -B -m unittest discover -v -s make-fnos/scripts/tests
```

测试会在临时目录生成 ext4 和 Btrfs 磁盘样本，并检查审计前后的输入 SHA-256。发布候选底包的核验方式见[镜像审计说明](../make-fnos/README.md#pr-0--官方底包审计)。

## 提交与 Pull Request

UMI 适配的提交标题采用 Conventional Commits，格式为 `type(scope): summary`，其中 `scope` 可省略。常见示例有 `fix(display): preserve CSOT backlight state`、`ci: validate device tree fixtures` 和 `docs: clarify serial enrollment`。

- 在 PR 中说明改动目的、影响的构建档位、执行过的命令和结果。涉及 boot、内核或设备树时，注明面板、内核版本及实际验证范围。
- 需要验证真机引导时，优先按[真机无刷写验收](04-真机无刷写验收.md)走 RAM 启动。提交日志前移除设备序列号、账号和密钥，并注明哪些功能仍待真机验证。
- 引用第三方代码或硬件资料时，保留原有版权信息，并在[许可与出处](../NOTICE.md)记录新增来源。请勿提交厂商固件、设备分区备份或访问凭据。
