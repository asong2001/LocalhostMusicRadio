# MusicRadio

MusicRadio 是一个面向 Linux 和 Docker 的本地音乐电台服务。它会读取本地音频目录，把 `flac`、`mp3`、`wav`、`m4a` 等文件连续播放，并实时转码成局域网可访问的 HLS 直播地址。

目标地址：

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

## 当前能力

- 扫描 `audio/` 目录下的常见音频文件。
- 支持循环播放和随机播放。
- 使用 FFmpeg 解码不同音频格式，并统一编码为 AAC HLS。
- 暴露 HLS 静态文件。
- 暴露 MP3 HTTP 直流，默认地址 `/stream.mp3`。
- 暴露 Web 控制台，默认端口 `8001`。
- Web 控制台支持修改扫描目录，新目录必须已经存在且服务进程可读。
- 提供简单 API：
  - `GET /api/status`
  - `POST /api/skip`
  - `POST /api/rescan`
- 提供 Dockerfile 和 Docker Compose 配置。

## 目录结构

```text
MusicRadio/
  app/
    main.py
    player.py
    scanner.py
    server.py
    settings.py
  audio/
  public/
    hls/
  tests/
  Dockerfile
  docker-compose.yml
```

## Docker 运行

把音频文件放到：

```text
MusicRadio/audio/
```

启动：

```bash
docker compose up -d --build
```

也可以指定任意宿主机音频目录：

```bash
./scripts/start-docker.sh /mnt/music
```

传入的音频目录必须已经存在且当前用户可读。脚本不会自动创建 `/mnt/music` 这类系统目录。

或者手动指定：

```bash
RADIO_AUDIO_HOST_DIR=/mnt/music docker compose up -d --build
```

查看状态：

```bash
docker compose logs -f
```

如果构建时报类似下面的错误：

```text
failed to resolve source metadata for docker.io/library/python:3.12-slim
401 Unauthorized
```

说明 Docker 当前配置的镜像源或代理拒绝了访问。这个错误发生在拉取基础镜像阶段，和 MusicRadio 代码无关。可以先检查 Docker daemon 的 registry mirror 配置，或临时改用 Linux 原生运行方式验证服务。

播放地址：

```text
http://<Linux主机IP>:8000/hls/radio.m3u8
```

例如：

```text
http://192.168.0.100:8000/hls/radio.m3u8
```

控制台地址：

```text
http://192.168.0.100:8001/
```

## Linux 原生运行

安装 FFmpeg：

```bash
sudo apt update
sudo apt install -y ffmpeg python3
```

启动服务：

```bash
cd MusicRadio
python3 -m app.main
```

指定音频目录：

```bash
python3 -m app.main --audio-dir /mnt/music
```

指定 Web 控制台端口：

```bash
python3 -m app.main --audio-dir /mnt/music --web-port 8001
```

也可以使用启动脚本：

```bash
./scripts/start.sh /mnt/music
```

传入的音频目录必须已经存在且当前用户可读。默认不传参数时使用项目内的 `audio/` 目录。

如果脚本没有执行权限，先运行：

```bash
chmod +x scripts/start.sh scripts/start-docker.sh
```

## Windows 原生运行

当前机器如果已经安装 Python 和 FFmpeg，可以用 PowerShell 启动：

```powershell
.\scripts\start.ps1 -AudioDir "D:\Music"
```

也可以指定端口和播放模式：

```powershell
.\scripts\start.ps1 -AudioDir "D:\Music" -Port 9000 -Mode shuffle
```

## 配置项

通过环境变量配置：

```text
RADIO_AUDIO_DIR=/radio/audio
RADIO_PUBLIC_DIR=/radio/public
RADIO_HLS_DIR=/radio/public/hls
RADIO_HOST=0.0.0.0
RADIO_PORT=8000
RADIO_WEB_PORT=8001
RADIO_MODE=loop
RADIO_AUDIO_BITRATE=128k
RADIO_MP3_BITRATE=128k
RADIO_HLS_TIME=3
RADIO_HLS_LIST_SIZE=5
```

命令行参数也可以覆盖常用配置：

```bash
python3 -m app.main \
  --audio-dir /mnt/music \
  --host 0.0.0.0 \
  --port 8000 \
  --web-port 8001 \
  --mode loop
```

`RADIO_MODE` 可选：

```text
loop
shuffle
```

## API

查看状态：

```bash
curl http://localhost:8000/api/status
```

MP3 HTTP 直流：

```bash
curl -I http://localhost:8000/stream.mp3
```

跳过当前曲目：

```bash
curl -X POST http://localhost:8000/api/skip
```

重新扫描音频目录：

```bash
curl -X POST http://localhost:8000/api/rescan
```

## 播放客户端

推荐先用 VLC 验证：

```bash
vlc http://<host-ip>:8000/hls/radio.m3u8
```

iPhone Safari 通常可以直接播放 HLS。桌面 Chrome 如果要网页播放，后续可以加 HLS.js 页面。

## 注意事项

- HLS 会有几秒延迟，这是协议特性。
- HLS 默认使用 3 秒 TS 分片，并返回 `video/MP2T`，以兼容更挑剔的硬件播放器。
- Docker 部署时，`audio/` 默认只读挂载进容器。
- 防火墙需要放行 `8000` 端口。
- 服务启动后如果没有音频文件，会等待并定期重新扫描。
