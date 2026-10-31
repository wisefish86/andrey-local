from pathlib import Path
from unittest.mock import patch
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Track, distribute_blocks

def track(n):
    return Track(Path(f"/mock/{n}.mp3"), "Singer", str(n), str(n), "сл-1",
                 "Я-англ" if n % 2 else "Я-рус", "", "", "г-1-База",
                 "", "", (), work_id=f"в-{n}")

class Limits(unittest.TestCase):
    def test_large_catalog_never_overflows_last_block(self):
        with patch("core.track_minutes", return_value=4.0):
            groups = distribute_blocks([track(i) for i in range(100)], 4, 25)
        self.assertEqual(len(groups), 4)
        for main, _ in groups:
            self.assertLessEqual(4 * len(main), 25)
            self.assertEqual({t.language for t in main}, {"Я-рус", "Я-англ"})

if __name__ == "__main__":
    unittest.main()
