import logging
from collections import Counter
from typing import TYPE_CHECKING
from typing import Counter as CounterT
from typing import Dict, Iterator, Type

if TYPE_CHECKING:
	from pathlib import Path

class NoLexerFound(Exception):
	pass

class TokenizerPlugin(object):

	exceptions: Dict[Type[Exception], str]

	def _tokenize(self, path):
		# type: (Path, ) -> Iterator[str]

		raise NotImplementedError

	def tokenize(self, path):
		# type: (Path, ) -> Counter

		c = Counter()  # type: CounterT[str]

		try:
			c.update(self._tokenize(path))
		except Exception as e:
			for exc, tpl in self.exceptions.items():
				if isinstance(e, exc):
					logging.warning(tpl.format(path=path, exc=e))
					break
			else:
				raise

		return c
