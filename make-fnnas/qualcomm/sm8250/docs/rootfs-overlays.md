# RootFS 文件层

`renas -b xiaomi-umi overlay` 按 `platform-files/qualcomm/sm8250/rootfs/` →
`different-files/xiaomi-umi/rootfs/` 的顺序，将 `make-fnnas/fnnas-files/` 中的对应文件复制到暂存根目录。
目前没有 Umi 与原有平台共用的覆盖文件。

现有 Umi 文件由 Debian 基线构建选用。接入官方 fnOS 时逐项确认登录、SSH、
网络和 systemd 的兼容性，再将核准的文件安装到目标镜像。
