from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from .player import RadioPlayer
from .server import create_server
from .settings import SettingsOverrides, load_settings
from .config_store import ConfigStore
from .stream_manager import StreamManager
from .web_server import create_web_server


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MusicRadio HLS service.")
    parser.add_argument("--audio-dir", help="Directory containing local audio files.")
    parser.add_argument("--public-dir", help="Directory served over HTTP.")
    parser.add_argument("--hls-dir", help="Directory where HLS files are written.")
    parser.add_argument("--config-path", help="Path to persistent radio JSON config.")
    parser.add_argument("--host", help="HTTP bind host, default: 0.0.0.0.")
    parser.add_argument("--port", type=int, help="HTTP bind port, default: 8000.")
    parser.add_argument("--web-port", type=int, help="Web control port, default: 8001.")
    parser.add_argument("--mode", choices=["loop", "shuffle"], help="Playback mode.")
    parser.add_argument("--ffmpeg-bin", help="FFmpeg executable path or command name.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    settings = load_settings(
        SettingsOverrides(
            audio_dir=args.audio_dir,
            public_dir=args.public_dir,
            hls_dir=args.hls_dir,
            config_path=args.config_path,
            host=args.host,
            port=args.port,
            web_port=args.web_port,
            mode=args.mode,
            ffmpeg_bin=args.ffmpeg_bin,
        )
    )
    manager = StreamManager(settings, ConfigStore(settings.config_path, settings))
    hls_httpd = create_server(settings, manager)
    web_httpd = create_web_server(settings, manager)

    def handle_signal(signum: int, _frame: object) -> None:
        logging.getLogger("musicradio").info("Received signal %s", signum)
        manager.stop()
        threading.Thread(target=hls_httpd.shutdown, daemon=True).start()
        threading.Thread(target=web_httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    manager.start()
    logging.getLogger("musicradio").info(
        "Serving HLS at http://%s:%s/hls/radio.m3u8; audio_dir=%s",
        settings.host,
        settings.port,
        settings.audio_dir,
    )
    logging.getLogger("musicradio").info(
        "Serving web control at http://%s:%s/",
        settings.host,
        settings.web_port,
    )
    web_thread = threading.Thread(target=web_httpd.serve_forever, name="web-server")
    web_thread.start()
    try:
        hls_httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hls_httpd.server_close()
        web_httpd.shutdown()
        web_thread.join(timeout=5)
        web_httpd.server_close()
        manager.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
