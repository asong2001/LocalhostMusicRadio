import unittest

from app.server import build_m3u_playlist


class ServerTests(unittest.TestCase):
    def test_build_m3u_playlist_contains_hls_and_mp3_urls(self) -> None:
        playlist = build_m3u_playlist(
            [
                ("MusicRadio HLS", "http://192.168.0.100:8000/hls/radio.m3u8"),
                ("MusicRadio MP3", "http://192.168.0.100:8000/stream.mp3"),
            ]
        )

        self.assertIn("#EXTM3U", playlist)
        self.assertIn("http://192.168.0.100:8000/hls/radio.m3u8", playlist)
        self.assertIn("http://192.168.0.100:8000/stream.mp3", playlist)


if __name__ == "__main__":
    unittest.main()
