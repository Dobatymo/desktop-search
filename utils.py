from __future__ import absolute_import, division, print_function, unicode_literals

import logging, tokenize
from collections import defaultdict, Counter
from operator import itemgetter
from importlib import import_module
from typing import TYPE_CHECKING

from genutility.exceptions import assert_choice
from genutility.file import read_file
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

if TYPE_CHECKING:
	from typing import Dict, Iterator, List

	from genutility.compat.pathlib import Path
	from pathspec import Patterns

def tokenize_python(path):
	# type: (str, ) -> Counter

	c = Counter()

	def asd():
		with tokenize.open(path) as fr:
			for type, string, start, end, line in tokenize.generate_tokens(fr.readline):
				if type == tokenize.NAME:
					yield string
	try:
		c.update(asd())
	except IndentationError as e:
		logging.warning("IndentationError in %s: %s", path, e)
	except tokenize.TokenError as e:
		logging.warning("TokenError in %s: %s", path, e)

	return c

def tokenize_javascript(path):
	# type: (str, ) -> Counter

	#from slimit.lexer import Lexer
	from calmjs.parse.lexers.es5 import Lexer
	from calmjs.parse.exceptions import ECMASyntaxError
	c = Counter()

	def asd():
		lexer = Lexer()

		content = read_file(path, "rt", encoding="utf-8")
		lexer.input(content)

		for token in lexer:
			if token.type == "ID":
				yield token.value

	try:
		c.update(asd())
	except UnicodeDecodeError:
		logging.warning("Skipping %s: file is not valid utf-8", path)
	except ECMASyntaxError:
		logging.warning("Skipping %s: file is not valid ES5", path)

	return c

def _gitignore_iterdir(path, spec):
	# type: (Path, Patterns) -> Iterator[Path]

	try:
		with (path / ".gitignore").open("r", encoding="utf-8") as fr:
			patterns = list(fr)

		cpatterns = list(map(GitWildMatchPattern, patterns)) + spec.patterns
		spec = PathSpec(cpatterns)

	except FileNotFoundError:
		pass

	for item in path.iterdir():
		if not spec.match_file(item):
			if item.is_file():
				yield item
			elif item.is_dir():
				yield from _gitignore_iterdir(item, spec)

def gitignore_iterdir(path, defaultignore=[".git"]):
	# type: (Path, Sequence[str]) -> Iterator[Path]

	spec = PathSpec(map(GitWildMatchPattern, defaultignore))
	return _gitignore_iterdir(path, spec)

def try_import(name, package=None):
	try:
		return import_module(name, package)
	except ImportError:
		return None

class InvertedIndex(object):

	def __init__(self):
		# type: () -> None

		self.modules = {
			".py": ([], []),
			".js": (["calmjs"], ["calmjs.parse"]),
		}

		self.tokenizers = {
			".py": tokenize_python,
			".js": tokenize_javascript,
		}

		for k, (modnames, realnames) in self.modules.items():
			assert len(modnames) == len(realnames)
			for modname, realname in zip(modnames, realnames):
				if not try_import(modname):
					logging.warning("Missing module: %s. Removing handler for: %s", realname, k)
					self.tokenizers.pop(k, None)

		self.clear()

	def clear(self):
		# type: () -> None

		self.docs2ids = {}  # type: Dict[Path, int]
		self.ids2docs = {}  # type: Dict[int, Path]
		self.index = defaultdict(list)

	def add_document(self, path):
		# type: (Path, ) -> int

		ret = 0

		try:
			freqs = self.tokenizers[path.suffix](path)
		except KeyError:
			logging.debug("Ignoring %s", path)
		else:
			doc_id = self.docs2ids.setdefault(path, len(self.docs2ids))
			self.ids2docs[doc_id] = path
			for token, freq in freqs.items():
				self.index[token].append((doc_id, freq))
			ret = len(freqs)

		return ret

	def search_token(self, token, sortby="path"):
		# type: (str, str) -> List[Path]

		assert_choice("sortby", sortby, {"path", "freq"})

		docs = self.index.get(token, [])  # get() does not insert key into defaultdict

		if sortby == "path":
			return sorted(self.ids2docs[doc_id] for doc_id, freq in docs)
		elif sortby == "freq":
			return [self.ids2docs[doc_id] for doc_id, freq in sorted(docs, key=itemgetter(1), reverse=True)]

class Indexer(object):

	def __init__(self, invindex):
		self.invindex = invindex
		self.paths = [] # type: List[Path]

	def index(self, gitignore=False, progressfunc=None):
		# type: (bool, Callable[[str], Any]) -> int

		""" Searches Indexer.paths for indexable files and indexes them.
			Returns the number of files added to the index.
		"""

		self.invindex.clear()

		docs = 0

		for path in self.paths:

			if gitignore:
				it = gitignore_iterdir(path)
			else:
				it = path.rglob("*")

			for filename in it:
				if self.invindex.add_document(filename):
					docs += 1
				if progressfunc:
					progressfunc(filename)

		return docs
