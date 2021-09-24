from __future__ import annotations, generator_stop

import tokenize
from typing import TYPE_CHECKING, Iterator, Tuple

from plugin import TokenizerPlugin

if TYPE_CHECKING:
    from pathlib import Path


class PythonPlugin(TokenizerPlugin):

    suffixes = {".py", ".pyw"}

    exceptions = {
        IndentationError: "IndentationError in {path}: {exc}",
        tokenize.TokenError: "TokenError in {path}: {exc}",
        SyntaxError: "SyntaxError in {path}: {exc}",
    }

    def _tokenize(self, path: Path) -> Iterator[Tuple[str, str]]:

        code_tokens = (tokenize.NAME, tokenize.NUMBER)
        text_tokens = (tokenize.STRING, tokenize.COMMENT)

        with tokenize.open(path) as fr:
            for type, string, start, end, line in tokenize.generate_tokens(fr.readline):
                if type in code_tokens:
                    yield "code", string
                elif type in text_tokens:
                    yield "text", string
