from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Track, unique_songs, version_length

def track(name):
    return Track(path=Path("/library/Song _____ Artist") / name,
                 artist="Artist", title="Song", clean_title="Song",
                 difficulty="", language="Я-рус", energy="", role="",
                 status="", rating="", bpm="", tags=(), work_id="в-Song")

class VersionTests(unittest.TestCase):
    def test_s_beats_f_even_if_full_arrives_first(self):
        full = track("Song [F] _____ Artist ֎ full.mp3")
        short = track("Song [S] _____ Artist ֎ short.mp3")
        self.assertEqual(version_length(short), "S")
        self.assertEqual(version_length(full), "F")
        self.assertEqual(unique_songs([full, short]), [short])
        self.assertEqual(unique_songs([short, full]), [short])

    def test_without_s_keeps_f(self):
        full = track("Song [F] _____ Artist ֎ full.mp3")
        ordinary = track("Song _____ Artist ֎ standard.mp3")
        self.assertEqual(unique_songs([ordinary, full]), [full])

if __name__ == "__main__":
    unittest.main()
