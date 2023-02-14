from pathlib import Path
from unittest import TestCase

from genutility.test import parametrize

from backends.memory import InvertedIndexMemory
from utils import CodeAnalyzer


class MemoryTest(TestCase):
    @parametrize(
        (True,),
        (False,),
    )
    def test_memory(self, keep_docs):
        analyzer = CodeAnalyzer()
        iim = InvertedIndexMemory(analyzer, keep_docs=keep_docs)

        truth = True
        result = iim.add_document_freqs(Path("test.py"), {"code": {}, "text": {"hello": 1, "world": 1}})
        self.assertEqual(truth, result)

        truth = {0: 1}
        result = iim.get_docs("text", "hello")
        self.assertEqual(truth, result)

        iim.remove_document(Path("test.py"))

        truth = {}
        result = iim.get_docs("text", "hello")
        self.assertEqual(truth, result)
