# RootFS 文件层

组装阶段按 `common-files/rootfs/` → `platform-files/qualcomm/sm8250/rootfs/` →
`different-files/xiaomi-umi/rootfs/` 覆盖，每层从其 `tools/legacy/rootfs/` 目录映射到目标根目录。
这里的 README 只描述来源和归属。

现有 Umi 文件由 Debian 基线构建选用。接入官方 fnOS 时逐项确认登录、SSH、
网络和 systemd 的兼容性，再将核准的文件安装到目标镜像。
