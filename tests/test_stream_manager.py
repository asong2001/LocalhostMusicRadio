from pathlib import Path
import tempfile
import time
import unittest

from app.config_store import ConfigStore, RadioConfig, StreamConfig
from app.stream_manager import StreamManager
from test_player import make_settings


class StreamManagerTests(unittest.TestCase):
    def test_create_stream_rejects_duplicate_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            manager = StreamManager(settings, ConfigStore(settings.config_path, settings))

            with self.assertRaises(ValueError):
                manager.create_stream({"id": "default", "name": "Default", "format": "m3u8"})

    def test_playlist_entries_only_include_enabled_streams(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            manager = StreamManager(settings, ConfigStore(settings.config_path, settings))
            manager.create_stream({"id": "off", "name": "Off", "format": "mp3", "enabled": False})

            entries = manager.playlist_entries("127.0.0.1", 8000)

        self.assertTrue(all("off" not in url for _, url in entries))
        self.assertTrue(any("/hls/radio.m3u8" in url for _, url in entries))

    def test_library_uses_cache_until_explicit_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "audio" / "music").mkdir(parents=True)
            (root / "audio" / "music" / "song.mp3").write_bytes(b"audio")
            settings = make_settings(root)
            manager = StreamManager(settings, ConfigStore(settings.config_path, settings))

            self.assertEqual(manager.library()["files"], [])
            manager.rescan_library()
            deadline = time.time() + 2
            while time.time() < deadline and manager.library()["scanning"]:
                time.sleep(0.01)

            files = manager.library()["files"]

        self.assertEqual([item["path"] for item in files], ["music/song.mp3"])

    def test_compatible_stream_uses_first_selected_stream_when_default_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            store = ConfigStore(settings.config_path, settings)
            store.save(
                RadioConfig(
                    library_dir=str(settings.audio_dir),
                    streams=[
                        StreamConfig(id="default", name="Default", format="m3u8", selected_files=[]),
                        StreamConfig(id="custom", name="Custom", format="m3u8", selected_files=["song.mp3"]),
                        StreamConfig(id="default-mp3", name="Default MP3", format="mp3", selected_files=[]),
                        StreamConfig(id="custom-mp3", name="Custom MP3", format="mp3", selected_files=["song.mp3"]),
                    ],
                )
            )
            manager = StreamManager(settings, store)

        self.assertEqual(manager.compatible_stream_id("m3u8"), "custom")
        self.assertEqual(manager.compatible_stream_id("mp3"), "custom-mp3")


if __name__ == "__main__":
    unittest.main()
