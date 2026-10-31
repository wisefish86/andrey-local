from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Track, build_language_balanced_list, arrange_vocal_block, difficulty_level, display_rating

def song(index, language="Я-рус", difficulty="сл-1"):
    return Track(path=Path("/mock") / (str(index) + ".mp3"), artist="Singer",
                 title=str(index), clean_title=str(index), difficulty=difficulty,
                 language=language, energy="", role="", status="г-1-База",
                 rating="196", bpm="", tags=(), work_id="в-" + str(index))

class SelectionPacingTests(unittest.TestCase):
    def test_balanced_language_and_alternation(self):
        pool = [song(i, "Я-англ") for i in range(8)] + [song(i + 8) for i in range(8)]
        chosen = build_language_balanced_list([], pool, 12, 50, 10)
        self.assertEqual(len(chosen), 12)
        english = sum(x.language == "Я-англ" for x in chosen)
        self.assertTrue(5 <= english <= 7)
        self.assertGreaterEqual(sum(a.language != b.language for a, b in zip(chosen, chosen[1:])), 9)

    def test_short_catalog_falls_back_without_repeats(self):
        pool = [song(i, "Я-англ") for i in range(3)] + [song(4)]
        chosen = build_language_balanced_list([], pool, 10, 50, 10)
        self.assertEqual(len(chosen), 4)
        self.assertEqual(len({x.work_id for x in chosen}), 4)

    def test_first_block_easy_opener_and_medium_limit(self):
        pool = [song(i, difficulty=level) for i, level in enumerate(
            ["сл-2", "сл-3", "сл-2", "сл-1", "сл-2", "сл-1", "сл-4", "сл-1"])]
        arranged = arrange_vocal_block(pool, first_block=True)
        self.assertEqual(difficulty_level(arranged[0]), 1)
        self.assertEqual({x.path for x in arranged}, {x.path for x in pool})
        for index in range(len(arranged) - 1):
            if difficulty_level(arranged[index]) >= 3 and any(difficulty_level(x) == 1 for x in arranged[index + 1:]):
                self.assertEqual(difficulty_level(arranged[index + 1]), 1)

    def test_rating_display_does_not_change_raw(self):
        self.assertEqual(display_rating("242"), "5/5")
        self.assertEqual(display_rating("196"), "4/5")
        self.assertEqual(display_rating("128"), "3/5")
        self.assertEqual(display_rating(""), "—")

if __name__ == "__main__":
    unittest.main()
