from __future__ import annotations, generator_stop

from typing import TYPE_CHECKING, Any, Dict, Iterator, Optional, Tuple

from genutility.file import read_file
from pygments.lexers import get_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound

from nlp import Preprocess
from plugin import NoLexerFound, TokenizerPlugin

if TYPE_CHECKING:
    from pathlib import Path


class PygmentsPlugin(TokenizerPlugin):

    suffixes = [".rs", ".c", ".cpp", ".htm", ".html", ".pyx", ".pxd", ".pxi"]

    exceptions = {
        UnicodeDecodeError: "Skipping {path}: file is not valid utf-8",
    }

    def __init__(self, preprocess: Preprocess, config: Optional[Dict[str, Any]] = None):
        TokenizerPlugin.__init__(self, preprocess, config)
        self.cache: Dict[str, Any] = {}

    def _tokenize(self, path: Path) -> Iterator[Tuple[str, str]]:

        try:
            lexer = self.cache[path.suffix]
        except KeyError:
            try:
                lexer = self.cache[path.suffix] = get_lexer_for_filename(path.name)
            except ClassNotFound:
                raise NoLexerFound()

        text = read_file(path, "rt", encoding="utf-8")

        for tokentype, value in lexer.get_tokens(text):
            if tokentype in Token.Name or tokentype in Token.Number:
                yield "code", value
            elif tokentype in Token.String or tokentype in Token.Comment:
                yield "text", value
