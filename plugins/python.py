import tokenize

from plugin import TokenizerPlugin, NoLexerFound

class PythonPlugin(TokenizerPlugin):

	suffixes = {".py", ".pyw"}

	exceptions = {
		IndentationError: "IndentationError in {path}: {exc}",
		tokenize.TokenError: "TokenError in {path}: {exc}",
	}

	def _tokenize(self, path):
		# type: (str, ) -> Iterator[str]

		with tokenize.open(path) as fr:
			for type, string, start, end, line in tokenize.generate_tokens(fr.readline):
				if type == tokenize.NAME:
					yield string
