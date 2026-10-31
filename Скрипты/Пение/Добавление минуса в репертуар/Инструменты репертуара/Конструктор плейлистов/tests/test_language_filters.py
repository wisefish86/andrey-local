from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Track, eligible_for_restaurant, build_language_balanced_list, song_key

def song(name, language):
    return Track(path=Path("/test/" + name + ".mp3"), artist=name, title=name,
                 clean_title=name, difficulty="сл-2", language=language,
                 energy="к-Сред", role="", status="г-1-База",
                 rating="", bpm="", tags=(), work_id="в-" + name)

class FiltersTests(unittest.TestCase):
    def test_chips_are_and_across_groups(self):
        a = song("A", "Я-англ")
        preset = {"language_allow": ["Я-англ"], "difficulty_allow": ["сл-2"],
                  "energy_allow": ["к-Сред"]}
        self.assertTrue(eligible_for_restaurant(a, preset))
        self.assertFalse(eligible_for_restaurant(replace(a, language="Я-рус"), preset))
        self.assertFalse(eligible_for_restaurant(replace(a, energy="к-Драйв"), preset))

    def test_balanced_addition_keeps_manual_choices(self):
        available = [song("E1", "Я-англ"), song("E2", "Я-англ"),
                     song("R1", "Я-рус"), song("R2", "Я-рус")]
        chosen = build_language_balanced_list([available[2]], available, 4, 50)
        self.assertEqual(chosen[0], available[2])
        self.assertEqual(sum(x.language == "Я-англ" for x in chosen), 2)
        self.assertEqual(len({song_key(x) for x in chosen}), 4)

if __name__ == "__main__":
    unittest.main()
