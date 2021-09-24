from __future__ import annotations, generator_stop

from typing import TYPE_CHECKING, Iterator, Tuple

from plugin import TokenizerPlugin

if TYPE_CHECKING:
    from pathlib import Path


class PlaintextPlugin(TokenizerPlugin):

    suffixes = {".txt", ".md"}
    maxfilesize = 1000000  # see spacy `nlp.max_length`

    exceptions = {
        ValueError: "ValueError in <{path}>: {exc}",
    }

    def _tokenize(self, path: Path) -> Iterator[Tuple[str, str]]:

        filesize = path.stat().st_size
        if filesize > self.maxfilesize:
            raise ValueError(f"File exceeds maximum filesize ({filesize} > {self.maxfilesize})")

        with open(path, "rt", encoding="utf-8") as fr:
            yield "text", fr.read()
