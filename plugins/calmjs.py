#from slimit.lexer import Lexer
from calmjs.parse.lexers.es5 import Lexer
from calmjs.parse.exceptions import ECMASyntaxError

from genutility.file import read_file

from plugin import TokenizerPlugin


class CalmjsPlugin(TokenizerPlugin):

	suffixes = [".js"]

	exceptions = {
		IndentationError: "Skipping {path}: file is not valid utf-8",
		ECMASyntaxError: "Skipping {path}: file is not valid ES5",
	}

	def _tokenize(self, path):
		# type: (str, ) -> Iterator[str]

		lexer = Lexer()
		text = read_file(path, "rt", encoding="utf-8")
		lexer.input(text)

		for token in lexer:
			if token.type == "ID":
				yield token.value
