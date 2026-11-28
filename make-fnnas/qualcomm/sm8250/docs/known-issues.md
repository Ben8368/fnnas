# Umi 原生镜像已知问题

本文件记录在真机上确认、尚未修复的原生镜像问题。记录只用于存档和排期，不代表已修复或已验收；原始 journal 留在本地，不随本文件提交。

## WebDAV / FTP 不可用：TLS 证书门禁

- 发现日期：2026-11-27
- 镜像：source `bc01c8b`，Linux `6.18.65`，profile `csot-90`，RootFS UUID `233f7317-1679-43a1-89f8-da0f85f11aa6`
- 现象：在 fnOS WebUI 开启 WebDAV 和 FTP，两项均报错；对应的 systemd 服务实际被跳过。
- 影响：WebDAV、FTP 不可用；Samba `smbd` 正常。
- 状态：已知问题，未修复。与同期内核改动（音频、PCIe）无关，属于用户态/原生镜像适配。

### journal 证据

- `webdav.service - WebDAV Service was skipped because of an unmet condition check (ConditionPathExists=/usr/trim/etc/ssl.crt/ca.crt).`
- `smbftpd.service - smbftpd was skipped because of an unmet condition check (ConditionPathExists=/usr/trim/etc/ssl.crt/ca.crt).`（开启 FTP 时再次出现）
- `share_service: webdav: no process found`
- `share_service: smbftpd: no process found`
- `systemctl: smbftpd.service is not active, cannot reload.`

### 镜像与单元证据

- 镜像中 `/usr/trim/etc/ssl.crt/` 目录不存在；`/usr/trim/etc/` 只有 `rsa_private_key.pem`、`rsa_public_key.pem`、`network_gateway_cert.conf` 等文件。
- `/etc/systemd/system/webdav.service` 的 `ExecStart=/usr/trim/bin/webdav`；`/etc/systemd/system/smbftpd.service` 的 `ExecStart=/usr/trim/bin/smbftpd -D`。
- 两个服务都有 `90-umi-compat.conf` drop-in，内容为：
  ```
  [Unit]
  ConditionPathExists=/usr/trim/etc/ssl.crt/ca.crt
  ```
- 二进制期望的路径：
  - `webdav`：`/usr/trim/etc/ssl.crt/ca.crt`、`/usr/trim/etc/ssl.key/ca.key`
  - `smbftpd`：`/usr/trim/etc/ssl.crt/server.crt`

### 根因

`make-fnnas/qualcomm/sm8250/scripts/native-rootfs.py` 中的 `TLS_CERT` 和 `NATIVE_SERVICE_POLICY` 为 `webdav.service`、`smbftpd.service` 生成上述条件；原生镜像没有提供 fnOS 的 TLS 证书/密钥目录，因此两个服务被 systemd 跳过。WebUI 的开启动作仍会尝试启动/重载服务，表现为报错。

### 后续方向（未实施）

- 在原生镜像中补受控的 `ssl.crt` / `ssl.key` 目录，或
- 为 WebDAV / FTP 提供不依赖 `ca.crt` 的受控服务适配；两种方案都需要单独验收，不并入内核改动。
