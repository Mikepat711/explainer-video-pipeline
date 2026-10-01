"""Spoken-form normalization: what the TTS engine actually receives."""
import unittest

from explainer.textnorm import normalize


class TextNormTests(unittest.TestCase):
    def check(self, cases):
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(normalize(text), want)

    def test_money_is_spoken_before_numbers(self):
        self.check([
            ("Wind offers $0, nuclear $20.", "Wind offers zero dollars, nuclear twenty dollars."),
            ("It asks $60 a megawatt-hour.", "It asks sixty dollars a megawatt-hour."),
            ("The price is $60/MWh.", "The price is sixty dollars per megawatt-hour."),
            ("Just $1 total.", "Just one dollar total."),
            ("It costs $2.50.", "It costs two dollars and fifty cents."),
            ("About $0.12 a unit.", "About twelve cents a unit."),
            ("A $1.5 billion upgrade.", "A one point five billion dollars upgrade."),
            ("Fees of €40 and £10.", "Fees of forty euros and ten pounds."),
        ])

    def test_dates_and_years(self):
        self.check([
            ("On April 1, 1997, PJM opened.", "On April first, nineteen ninety-seven, PJM opened."),
            ("It started July 4.", "It started July fourth."),
            ("It began in 1927.", "It began in nineteen twenty-seven."),
            ("Demand grew after 2009.", "Demand grew after two thousand nine."),
            ("From 1990-2000 it doubled.", "From nineteen ninety to two thousand it doubled."),
            ("Since the 1960s.", "Since the nineteen sixties."),
        ])

    def test_hyphen_after_a_letter_is_not_a_minus_sign(self):
        self.check([
            ("That rule is called N-1.", "That rule is called N minus one."),
            ("The F-35 and COVID-19.", "The F thirty-five and COVID nineteen."),
            ("Swings of -0.05 Hz.", "Swings of minus zero point zero five hertz."),
            ("A 1-2 second gap.", "A one to two second gap."),
        ])

    def test_acronym_plurals_and_word_acronyms(self):
        self.check([
            ("These are ISOs, like CAISO.", "These are eye ess ohs, like Kaiso."),
            ("Europe has TSOs and the US has RTOs.", "Europe has tee ess ohs and the US has are tee ohs."),
            ("EVs and LEDs.", "ee vees and el ee dees."),
            ("PJM's market and ERCOT's grid.", "pee jay ems market and Ercot's grid."),
            ("Each ISO and EV here.", "Each I-S-O and E.V. here."),
            ("GPS still works.", "G.P.S. still works."),
            ("ISO-NE and MISO.", "I-S-O New England and My-so."),
        ])

    def test_units_and_symbols(self):
        self.check([
            ("It runs at 60 Hz.", "It runs at sixty hertz."),
            ("About 5% of 500 MW.", "About five percent of five hundred megawatts."),
            ("Roughly ~30 plants.", "Roughly about thirty plants."),
            ("This is Part 3.", "This is Part three."),
        ])


if __name__ == "__main__":
    unittest.main()
