from pygments.token import Token
from pygments.lexers import get_lexer_for_filename
from pygments.util import ClassNotFound
#from pygments.lexers.rust import RustLexer

from genutility.file import read_file

from plugin import TokenizerPlugin, NoLexerFound

class PygmentsPlugin(TokenizerPlugin):

	suffixes = [".rs", ".c", ".cpp", ".htm", ".html"]

	exceptions = {
		UnicodeDecodeError: "Skipping {path}: file is not valid utf-8",
	}

	def __init__(self):
		TokenizerPlugin.__init__(self)
		self.cache = {}

	def _tokenize(self, path):
		# type: (str, ) -> Iterator[str]

		try:
			lexer = self.cache[path.suffix]
		except KeyError:
			try:
				lexer = self.cache[path.suffix] = get_lexer_for_filename(path.name)
			except ClassNotFound:
				raise NoLexerFound()

		#lexer = RustLexer()
		text = read_file(path, "rt", encoding="utf-8")

		for tokentype, value in lexer.get_tokens(text):
			if tokentype in Token.Name:
				yield value
