from __future__ import absolute_import, division, print_function, unicode_literals

import logging, tokenize
from collections import defaultdict
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

class InvalidDocument(KeyError):
	pass

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

class InvertedIndex(object):

	lexers = {
		"calmjs": "CalmjsPlugin",
		"python": "PythonPlugin",
		"pygments": "PygmentsPlugin",
	}

	def __getstate__(self):
		state = self.__dict__.copy()
		del state["tokenizers"]
		return state

	def __setstate__(self, state):
		self.__dict__.update(state)
		self.tokenizers = self._get_tokenizers()

	def __init__(self, keep_docs=True):
		# type: () -> None

		""" Set `keep_docs=False` to improve memory usage,
			but decrease `remove_document()` performance.
		"""

		self.keep_docs = keep_docs
		self.tokenizers = self._get_tokenizers()

		logging.info("Found lexers for: [%s]", ", ".join(self.tokenizers.keys()))

		self.clear()

	def _get_tokenizers(self):
		# type: () -> Dict[str, TokenizerPlugin]

		tokenizers = {}  # type: Dict[str, TokenizerPlugin]

		for modname, clsname in self.lexers.items():
			try:
				module = import_module("plugins.{}".format(modname))
			except ImportError as e:
				logging.warning("Could not import %s: %s", modname, e)
				continue

			obj = getattr(module, clsname)()
			for suffix in obj.suffixes:
				try:
					obj = tokenizers[suffix]
					logging.warning("%s already handled by plugins/%s", suffix, modname)
				except KeyError:
					tokenizers[suffix] = obj
		
		return tokenizers

	def clear(self):
		# type: () -> None

		self.docs2ids = {}  # type: Dict[Path, int]
		self.ids2docs = {}  # type: Dict[int, Path]
		self.index = defaultdict(dict)  # type: Dict[str, Dict[int, int]]
		self.doc_freqs = {}  # type: Dict[int, Dict[str, int]]

	def add_document(self, path):
		# type: (Path, ) -> int

		ret = 0

		try:
			lexer = self.tokenizers[path.suffix]
		except KeyError:
			logging.debug("Ignoring %s", path)
		else:
			freqs = lexer.tokenize(path)
			doc_id = self.docs2ids.setdefault(path, len(self.docs2ids))
			self.ids2docs[doc_id] = path
			if self.keep_docs:
				self.doc_freqs[doc_id] = freqs
			for token, freq in freqs.items():
				self.index[token][doc_id] = freq
			ret = len(freqs)

		return ret

	def remove_document(self, path):
		# type: (Path, ) -> None

		""" If `InvertedIndex` was created with `keep_docs=True`,
			the complexity is O(number of unique tokens in document).
			If created with `keep_docs=False`,
			the complexity is O(number of tokens in index)
		"""

		try:
			doc_id = self.docs2ids[path]
		except KeyError:
			raise InvalidDocument()

		if self.keep_docs:
			for token, freq in self.doc_freqs[doc_id].items():
				del self.index[token][doc_id]
		else:
			for token, freqs in self.index.items():
				freqs.pop(doc_id, None)

	def _sorted(self, paths, sortby="path"):
		assert_choice("sortby", sortby, {"path", "freq"})

		if sortby == "path":
			return sorted(paths, key=itemgetter(0), reverse=False)
		elif sortby == "freq":
			return sorted(paths, key=itemgetter(1), reverse=True)

	def search_token(self, token, sortby="path"):
		# type: (str, str) -> List[Tuple[Path, int]]

		docs = self.index.get(token, {})  # get() does not insert key into defaultdict
		paths = ((self.ids2docs[doc_id], freq) for doc_id, freq in docs.items())

		return self._sorted(paths, sortby)

	def search_tokens_op(self, tokens, setop, sortby="path"):
		# type: (Sequence[str], Callable[[*set], set], str) -> List[Tuple[Path, int]]

		freqs = defaultdict(int)

		for token in tokens:
			for doc_id, freq in self.index.get(token, {}).items():
				freqs[doc_id] += freq

		sets = tuple(set(self.index.get(token, {}).keys()) for token in tokens)
		docs = setop(*sets)
		paths = ((self.ids2docs[doc_id], freqs[doc_id]) for doc_id in docs)

		return self._sorted(paths, sortby)

	def search_tokens_and(self, tokens, sortby="path"):
		# type: (Sequence[str], str) -> List[Tuple[Path, int]]

		return self.search_tokens_op(tokens, set.intersection, sortby)

	def search_tokens_or(self, tokens, sortby="path"):
		# type: (Sequence[str], str) -> List[Tuple[Path, int]]

		return self.search_tokens_op(tokens, set.union, sortby)

class Indexer(object):

	def __init__(self, invindex):
		self.invindex = invindex
		self.paths = [] # type: List[Path]
		self.mtimes = {} # type: Dict[Path, int]

	def index(self, suffixes=None, partial=True, gitignore=False, progressfunc=None):
		# type: (Set[str], bool, bool, Callable[[str], Any]) -> int

		""" Searches Indexer.paths for indexable files and indexes them.
			Returns the number of files added to the index.
		"""

		if not partial:
			self.invindex.clear()
			add = True

		docs = 0

		for path in self.paths:

			if gitignore:
				it = gitignore_iterdir(path)
			else:
				it = path.rglob("*")

			for filename in it:

				if suffixes:
					if filename.suffix not in suffixes:
						continue

				if partial:
					new_mtime = filename.stat().st_mtime

					try:
						old_mtime = self.mtimes[filename]
					except KeyError:
						self.mtimes[filename] = new_mtime
						add = True
					else:
						if old_mtime == new_mtime:
							add = False
						else:
							try:
								self.invindex.remove_document(filename)
							except InvalidDocument:
								pass
							self.mtimes[filename] = new_mtime
							add = True

				if add:
					if self.invindex.add_document(filename):
						docs += 1
					if progressfunc:
						progressfunc(filename)

		return docs
