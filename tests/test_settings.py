from pathlib import Path
import unittest

from app.settings import SettingsOverrides, load_settings


class SettingsTests(unittest.TestCase):
    def test_cli_overrides_audio_dir(self) -> None:
        settings = load_settings(SettingsOverrides(audio_dir="/tmp/musicradio-audio"))

        self.assertEqual(settings.audio_dir, Path("/tmp/musicradio-audio").resolve())

    def test_cli_overrides_port_and_mode(self) -> None:
        settings = load_settings(SettingsOverrides(port=9000, web_port=9001, mode="shuffle"))

        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.web_port, 9001)
        self.assertEqual(settings.mode, "shuffle")


if __name__ == "__main__":
    unittest.main()
