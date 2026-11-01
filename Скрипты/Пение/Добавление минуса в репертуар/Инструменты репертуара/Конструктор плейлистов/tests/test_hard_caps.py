from pathlib import Path
from unittest.mock import patch
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Track, distribute_blocks, validate_hard_spacing, difficulty_level

def song(n, level):
    return Track(Path(f"/fake/{n}.mp3"), "Singer", str(n), str(n),
                 f"сл-{level}", "Я-рус" if n % 2 else "Я-англ",
                 "", "", "г-1-База", "", "", (), work_id=f"в-{n}")

class HardCaps(unittest.TestCase):
    def test_never_three_hard_tracks_in_one_block(self):
        songs = [song(i, 3) for i in range(8)] + [song(i+8, 1) for i in range(12)]
        with patch("core.track_minutes", return_value=3.0):
            blocks = distribute_blocks(songs, 4, 25)
        for main, _ in blocks:
            self.assertLessEqual(sum(difficulty_level(t) >= 3 for t in main), 2)
            self.assertTrue(validate_hard_spacing(main))

    def test_requires_easy_between_two_hard(self):
        self.assertFalse(validate_hard_spacing([song(1,3), song(2,2), song(3,4)]))
        self.assertTrue(validate_hard_spacing([song(1,3), song(4,1), song(3,4)]))

if __name__ == "__main__":
    unittest.main()
