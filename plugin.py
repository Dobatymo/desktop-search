import logging

from collections import Counter

class NoLexerFound(Exception):
	pass

class TokenizerPlugin(object):

	def _tokenize(self, path):
		# type: (str, ) -> Iterator[str]

		raise NotImplementedError

	def tokenize(self, path):
		# type: (Path, ) -> Counter

		c = Counter()

		try:
			c.update(self._tokenize(path))
		except Exception as e:
			for exc, tpl in self.exceptions.items():
				if isinstance(e, exc):
					logging.warning(tpl.format(path=path, exc=exc))
					break
			else:
				raise

		return c
