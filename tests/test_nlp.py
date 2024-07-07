from collections import Counter
from unittest import TestCase

from nlp import DEFAULT_CONFIG, Preprocess

TEXTS = ["", "I'm a software engineer!", "def test_text(self):"]
PP_TEXTS = [[], ["i", "'m", "a", "software", "engineer", "!"], ["def", "test_text(self", "):"]]
PP_CODES = [[], ["I'm", "a", "software", "engineer!"], ["def", "test_text(self):"]]


class PreprocessTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pp = Preprocess()

    def test_text(self):
        for text, truth in zip(TEXTS, PP_TEXTS):
            with self.subTest(text=text):
                result = self.pp.text(DEFAULT_CONFIG["text"], text)
                self.assertEqual(truth, result)

    def test_code(self):
        for code, truth in zip(TEXTS, PP_CODES):
            with self.subTest(code=code):
                result = self.pp.text(DEFAULT_CONFIG["code"], code)
                self.assertEqual(truth, result)

    def test_text_batch(self):
        truth = sum(map(Counter, PP_TEXTS), start=Counter())
        freqs = Counter()
        self.pp.batch(DEFAULT_CONFIG["text"], TEXTS, freqs)
        self.assertEqual(truth, freqs)

    def test_code_batch(self):
        truth = sum(map(Counter, PP_CODES), start=Counter())
        freqs = Counter()
        self.pp.batch(DEFAULT_CONFIG["code"], TEXTS, freqs)
        self.assertEqual(truth, freqs)
