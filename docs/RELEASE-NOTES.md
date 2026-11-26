# FnNAS 小米 10（UMI）发布说明模板

填写实际构建和测试结果后使用。小米 10 的仓库入口是 [Ben8368/fnnas](https://github.com/Ben8368/fnnas)，许可证和组件出处见 [LICENSE](../LICENSE) 和 [NOTICE](../NOTICE.md)。

## 构建信息

| 项目 | 填写内容 |
|---|---|
| 设备 | 小米 10（`xiaomi-umi`，Qualcomm SM8250） |
| 面板与刷新率 | CSOT 60 Hz 或 90 Hz，填写实际配置 |
| 内核 | 填写 Linux 版本及源码提交 |
| 用户态 | 填写 Debian 基线版本，或已经实机验证的 fnOS ARM64 底包版本 |
| RootFS | 填写文件系统、UUID 和镜像格式。仅发布内核时填「无」 |
| 构建来源 | 填写 FnNAS 提交、构建 Run ID、Attempt 和配置 |

## 附件

| 文件 | 用途 | SHA-256 |
|---|---|---|
| UMI 内核包 | 填写实际版本和 CSOT 档位 | 填写 |
| Boot 与 RootFS | 配套提供时填写实际文件名 | 填写 |
| 校验清单 | 填写实际文件名 | 按清单校验 |

## 验证范围

分别记录 RAM 探针、挂载和完整 RootFS 启动的结果。只有经过实机验证的项目才填「通过」。按实际情况列出 CSOT 显示、USB ACM、Wi-Fi、GPU、充电、fnOS WebUI 和 OTA 的验证范围。[无刷写验收流程](04-真机无刷写验收.md)

## 使用说明

保持 Boot 与 RootFS 同次构建配对，并按实际面板选择刷新率。保留设备现有的原厂 DTBO 和基带相关分区。仅验证启动链时使用 Fastboot RAM 启动。Debian 基线的首启登录和 SSH 设置见 [首次开机步骤](../tools/legacy/rootfs-build/BUILD.md#七首次开机后必做)。[机型说明](../README.umi.md) · [发布和校验](04-发布与下载.md)
