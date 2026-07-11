from pathlib import Path
import tempfile
import unittest

from app.mp3_stream import Mp3Stream
from test_player import make_settings


class Mp3StreamTests(unittest.TestCase):
    def test_build_command_outputs_mp3_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stream = Mp3Stream(make_settings(Path(temp_dir)))
            command = stream._build_command()

        self.assertIn("libmp3lame", command)
        self.assertIn("mp3", command)
        self.assertEqual(command[-1], "pipe:1")
        self.assertLess(command.index("-re"), command.index("-i"))


if __name__ == "__main__":
    unittest.main()
