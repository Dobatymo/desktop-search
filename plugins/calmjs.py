from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

# from slimit.lexer import Lexer
from calmjs.parse.exceptions import ECMASyntaxError
from calmjs.parse.lexers.es5 import Lexer
from genutility.file import read_file

from plugin import TokenizerPlugin

if TYPE_CHECKING:
    from pathlib import Path


class CalmjsPlugin(TokenizerPlugin):

    suffixes = [".js"]

    exceptions = {
        IndentationError: "Skipping {path}: file is not valid utf-8",
        ECMASyntaxError: "Skipping {path}: file is not valid ES5",
    }

    def _tokenize(self, path: Path) -> Iterator[tuple[str, str]]:

        lexer = Lexer(yield_comments=True)
        text = read_file(path, "rt", encoding="utf-8")
        lexer.input(text)

        code_tokens = ("ID", "NUMBER")
        text_tokens = ("STRING", "LINE_COMMENT", "BLOCK_COMMENT")

        for token in lexer:
            if token.type in code_tokens:
                yield "code", token.value
            elif token.type in text_tokens:
                yield "text", token.value
