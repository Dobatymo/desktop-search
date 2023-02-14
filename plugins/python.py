import tokenize
from pathlib import Path
from typing import Iterator, Tuple

from plugin import TokenizerPlugin


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
