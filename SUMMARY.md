# MusicRadio 项目总结

## 项目定位

MusicRadio 是一个本地音乐电台服务，用于读取 NAS 或 Linux 主机上的本地音频文件，并将它们连续转码为局域网可访问的 HLS 直播流。

典型使用场景：

```text
本地音乐目录 -> MusicRadio -> HLS m3u8 地址 -> VLC / 手机 / 浏览器 / 播放器
```

当前默认地址：

```text
http://<host-ip>:8000/hls/radio.m3u8
```

兼容 MP3 HTTP 直流：

```text
http://<host-ip>:8000/stream.mp3
```

Web 控制台：

```text
http://<host-ip>:8001/
```

## 已完成能力

- 支持扫描本地音频目录。
- 支持常见音频格式：`flac`、`mp3`、`wav`、`m4a`、`aac`、`ogg`、`opus` 等。
- 使用 FFmpeg 将不同来源音频统一解码为 PCM，再编码为 AAC HLS。
- 支持顺序循环播放和随机播放。
- 生成 HLS 直播文件：`radio.m3u8` 和 `.ts` 分片。
- 通过 HTTP 暴露 HLS 播放地址。
- 通过 HTTP 暴露连续 MP3 直播流，适合不稳定支持 HLS/AAC 的设备。
- 提供 Web 控制台，默认端口 `8001`。
- 控制台支持查看运行状态、当前曲目、队列数量、错误信息和直播地址。
- 控制台支持跳过当前曲目。
- 控制台支持重新扫描目录。
- 控制台支持修改扫描目录。
- 支持 Linux 原生运行。
- 提供 Dockerfile 和 docker-compose.yml。
- 提供 Windows、Linux、Docker 启动脚本。

## 关键设计

服务采用双 FFmpeg 管线：

```text
单曲 FFmpeg decoder -> 统一 PCM -> 常驻 FFmpeg encoder -> HLS
```

这样做的原因：

- 本地音乐文件格式、采样率、声道数可能不同。
- 直接拼接不同格式音频容易导致 HLS 流中断。
- 统一 PCM 后再编码，可以让直播流保持稳定。

为避免播放速度异常，encoder 输入使用 `-re`，让 FFmpeg 按真实播放时间读取音频流。

## NAS 实际部署路径

当前代码目录：

```text
/vol1/1000/home/MusicRadio
```

当前音乐目录：

```text
/vol2/1000/Download/音乐下载/music/散装音乐
```

推荐启动方式：

```bash
cd /vol1/1000/home/MusicRadio
nohup ./scripts/start.sh "/vol2/1000/Download/音乐下载/music/散装音乐" > musicradio.log 2>&1 &
```

查看日志：

```bash
tail -f musicradio.log
```

停止服务：

```bash
pkill -f "python3 -m app.main"
```

## API

HLS/API 服务默认运行在 `8000`：

```text
GET  /api/status
POST /api/skip
POST /api/rescan
```

Web 控制服务默认运行在 `8001`：

```text
GET  /
GET  /api/status
POST /api/skip
POST /api/rescan
POST /api/audio-dir
```

修改扫描目录示例：

```bash
curl -X POST http://localhost:8001/api/audio-dir \
  -H "Content-Type: application/json" \
  -d '{"audio_dir":"/vol2/1000/Download/音乐下载/music/散装音乐"}'
```

## 当前注意事项

- 桌面 Chrome/Edge 通常不能直接用原生 `<audio>` 播放 `.m3u8`，后续如果需要浏览器内播放，应加入 HLS.js。
- Docker 版本已经准备好，但 NAS 上 Docker 镜像源曾出现 `401 Unauthorized`，所以当前建议优先使用 Linux 原生运行。
- HLS 是直播分片协议，会天然存在几秒延迟。
- HLS 当前按兼容模式输出：3 秒 TS 分片、禁止缓存标签、`.ts` 返回 `video/MP2T`。
- 音频目录必须存在，并且服务进程需要有读取权限。
- 端口 `8000` 和 `8001` 需要在 NAS 或防火墙上允许局域网访问。

## 后续建议

- 增加 HLS.js，让 Web 控制台内置播放器在 Chrome/Edge 中可用。
- 增加 systemd service，让 NAS 重启后自动恢复服务。
- 增加播放队列页面，显示扫描到的曲目列表。
- 增加播放模式切换 API。
- 修复 Docker 镜像源后切换到 docker compose 长期部署。
