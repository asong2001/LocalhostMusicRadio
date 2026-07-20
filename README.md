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

Apple TV / IPTV 应用使用的 M3U 播放列表：

```text
http://<host-ip>:8000/playlist.m3u
```

Web 控制台：

```text
http://<host-ip>:8001/
```

多流地址示例：

```text
http://<host-ip>:8000/streams/default/hls/radio.m3u8
http://<host-ip>:8000/streams/default-mp3/stream.mp3
```

## 当前能力

- 扫描 `audio/` 目录下的常见音频文件。
- 支持多个独立流，每个流可选择 `m3u8` 或 `mp3` 输出。
- 支持循环播放和随机播放。
- 支持全局扫描音频库，并在 Web 控制台按复选框选择每个流的音频源。
- 支持将流配置和已选音频持久化到 `config/radio.json`。
- 使用 FFmpeg 解码不同音频格式，并统一编码为 AAC HLS。
- 暴露 HLS 静态文件。
- 暴露 MP3 HTTP 直流，默认地址 `/stream.mp3`。
- 暴露 M3U 播放列表，默认地址 `/playlist.m3u`。
- 暴露 Web 控制台，默认端口 `8001`。
- Web 控制台支持修改扫描目录，新目录必须已经存在且服务进程可读。
- Web 控制台支持在顺序循环和随机播放之间切换。
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

本项目可以直接构建成发布镜像。容器内固定使用这些目录：

```text
/radio/audio   音乐目录，只读挂载
/radio/public  HLS/M3U 运行输出，建议持久化
/radio/config  Web 配置和多流配置，必须持久化
```

本地构建镜像：

```bash
./scripts/docker-build.sh localhost-music-radio:latest
```

直接运行：

```bash
docker run -d \
  --name music-radio \
  --restart unless-stopped \
  -p 8000:8000 \
  -p 8001:8001 \
  -v /mnt/music:/radio/audio:ro \
  -v musicradio-public:/radio/public \
  -v musicradio-config:/radio/config \
  localhost-music-radio:latest
```

使用 Compose 部署：

```bash
cp .env.example .env
# 修改 .env 里的 RADIO_AUDIO_HOST_DIR
docker compose up -d --build
```

如果使用已经发布到镜像仓库的镜像，不需要源码构建：

```bash
cp .env.example .env
# 修改 .env 里的 MUSICRADIO_IMAGE 和 RADIO_AUDIO_HOST_DIR
docker compose -f docker-compose.release.yml up -d
```

指定任意宿主机音频目录：

```bash
RADIO_AUDIO_HOST_DIR=/mnt/music docker compose up -d --build
```

传入的音频目录必须已经存在且 Docker 服务可读。配置会保存在 `./config/radio.json`，升级容器时不会丢失电台列表和勾选结果。

查看状态：

```bash
docker compose logs -f
```

发布到镜像仓库：

```bash
./scripts/docker-publish.sh ghcr.io/asong2001/localhost-music-radio:latest
```

发布前需要先登录对应仓库，例如：

```bash
docker login ghcr.io
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
chmod +x scripts/start.sh scripts/start-docker.sh scripts/docker-build.sh scripts/docker-publish.sh
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
RADIO_CONFIG_PATH=/radio/config/radio.json
RADIO_HOST=0.0.0.0
RADIO_PORT=8000
RADIO_WEB_PORT=8001
RADIO_MODE=loop
RADIO_AUDIO_BITRATE=256k
RADIO_MP3_BITRATE=192k
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

M3U 播放列表：

```bash
curl http://localhost:8000/playlist.m3u
```

跳过当前曲目：

```bash
curl -X POST http://localhost:8000/api/skip
```

重新扫描音频目录：

```bash
curl -X POST http://localhost:8000/api/rescan
```

Web 控制台切换随机播放：

```bash
curl -X POST http://localhost:8001/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"shuffle"}'
```

多流管理 API：

```bash
curl http://localhost:8001/api/library
curl http://localhost:8001/api/streams
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
- Docker 部署时，音乐目录建议只读挂载进容器。
- Docker 部署必须持久化 `/radio/config`，否则容器重建后 Web 里的电台配置会丢失。
- 防火墙需要放行 `8000` 和 `8001` 端口。
- 服务启动后不会自动扫描全库，需要在 Web 控制台点击“重新扫描”。
