from pathlib import Path
import tempfile
import unittest

from app.player import RadioPlayer
from app.settings import Settings


def make_settings(root: Path) -> Settings:
    return Settings(
        audio_dir=root / "audio",
        public_dir=root / "public",
        hls_dir=root / "public" / "hls",
        host="0.0.0.0",
        port=8000,
        web_port=8001,
        mode="loop",
        ffmpeg_bin="ffmpeg",
        audio_bitrate="128k",
        sample_rate=44100,
        channels=2,
        hls_time=6,
        hls_list_size=8,
    )


class PlayerTests(unittest.TestCase):
    def test_encoder_reads_raw_pipe_in_realtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            player = RadioPlayer(make_settings(Path(temp_dir)))
            command = player._build_encoder_command()

        self.assertIn("-re", command)
        self.assertLess(command.index("-re"), command.index("-i"))

    def test_set_audio_dir_updates_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "music"
            audio_dir.mkdir()
            player = RadioPlayer(make_settings(root))

            resolved = player.set_audio_dir(audio_dir)
            snapshot = player.snapshot()

        self.assertEqual(resolved, audio_dir.resolve())
        self.assertEqual(snapshot["audio_dir"], str(audio_dir.resolve()))

    def test_set_audio_dir_rejects_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            player = RadioPlayer(make_settings(root))

            with self.assertRaises(ValueError):
                player.set_audio_dir(root / "missing")


if __name__ == "__main__":
    unittest.main()
