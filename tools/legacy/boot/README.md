# boot —— 配套 boot 镜像

本目录存放**配套的 boot 镜像**（Android boot header v2：kernel + initrd + DTB）。

| 文件 | 大小 | sha256 |
|---|---|---|
| `boot-umi-csot-ovf-wifi6-gpu-oc-final.img` | 28,209,152 B | `a7e4d341e35a663683bf41a8fe99d472bc6b8568aa1b54b05901dc7e9f2d842a` |

> ⚠️ **大体积镜像不在 git 仓库里**（二进制走 GitHub Releases，仓库只放源码/文档/脚本）。
> 见 [`../docs/qualcomm/sm8250/xiaomi-umi/04-发布与下载.md`](../../../docs/qualcomm/sm8250/xiaomi-umi/04-发布与下载.md)。

## 获取起点基线镜像（源自 `misaka-link/umi-linux`）

> 注：本项目暂未发布新的 fnOS 专用 `boot.img`，如需复现或测试起点基线，可从原基线仓库下载：

```bash
# 在仓库根目录执行
curl -LO https://github.com/misaka-link/umi-linux/releases/download/v2026-09-27/boot-umi-csot-ovf-wifi6-gpu-oc-final.img
mv boot-umi-csot-ovf-wifi6-gpu-oc-final.img tools/legacy/boot/
```

## 它有什么用

1. **刷机**（唯一必须的一步）：
   ```bash
   fastboot flash boot tools/legacy/boot/boot-umi-csot-ovf-wifi6-gpu-oc-final.img
   ```
2. **重建时的基底**：`bash tools/legacy/boot-build/build-boot.sh` 默认就以它当基底 ——
   只替换 dtb 段（kernel / ramdisk 逐字节不动），所以改 DTB 不用重新编内核。
   不放这个文件的话，`build-boot.sh` 会报错并要求你把基底作为参数传进去。

## 想自己重建

见 [`../boot-build/BUILD.md`](../boot-build/BUILD.md)：DTS 源在 [`../dtb/`](../dtb/)，
构建材料在 [`../boot-build/`](../boot-build/)。**实测可复现** —— 不改任何东西重跑，
产物 sha256 与上表一致。
