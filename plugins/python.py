import tokenize
from typing import TYPE_CHECKING, Iterator

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

	def _tokenize(self, path):
		# type: (Path, ) -> Iterator[str]

		with tokenize.open(path) as fr:
			for type, string, start, end, line in tokenize.generate_tokens(fr.readline):
				if type == tokenize.NAME:
					yield string
