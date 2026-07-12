from pathlib import Path
import tempfile
import unittest

from app.config_store import ConfigStore, StreamConfig, validate_stream_config
from test_player import make_settings


class ConfigStoreTests(unittest.TestCase):
    def test_default_config_creates_hls_and_mp3_streams(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            store = ConfigStore(settings.config_path, settings)

            config = store.load()

        self.assertEqual(config.streams[0].id, "default")
        self.assertEqual(config.streams[0].format, "m3u8")
        self.assertEqual(config.streams[1].id, "default-mp3")
        self.assertEqual(config.streams[1].format, "mp3")
        self.assertEqual(config.streams[0].selected_files, [])
        self.assertEqual(config.streams[1].selected_files, [])

    def test_duplicate_stream_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = make_settings(root)
            store = ConfigStore(settings.config_path, settings)
            config = store.load()
            duplicate = StreamConfig(id="default", name="重复", format="m3u8")

            with self.assertRaises(ValueError):
                store.save(type(config)(library_dir=config.library_dir, streams=[*config.streams, duplicate]))

    def test_stream_id_validation_rejects_unsafe_id(self) -> None:
        with self.assertRaises(ValueError):
            validate_stream_config(StreamConfig(id="中文", name="中文名", format="m3u8"))


if __name__ == "__main__":
    unittest.main()
