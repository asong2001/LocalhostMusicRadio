from pathlib import Path
import tempfile
import unittest

from app.scanner import scan_audio_files


class ScannerTests(unittest.TestCase):
    def test_scan_audio_files_filters_and_sorts_supported_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "b.mp3").write_bytes(b"")
            (root / "a.flac").write_bytes(b"")
            (root / "note.txt").write_text("ignore", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "c.WAV").write_bytes(b"")

            result = [path.name for path in scan_audio_files(root)]

        self.assertEqual(result, ["a.flac", "b.mp3", "c.WAV"])


if __name__ == "__main__":
    unittest.main()
