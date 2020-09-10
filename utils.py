from __future__ import absolute_import, division, print_function, unicode_literals

import logging, tokenize
from collections import defaultdict
from operator import itemgetter
from importlib import import_module
from itertools import chain
from typing import TYPE_CHECKING

from genutility.exceptions import assert_choice
from genutility.file import read_file
from genutility.compat.pathlib import Path
from genutility.compat.os import fspath
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

if TYPE_CHECKING:
	from typing import Dict, Iterator, List

	from pathspec import Patterns

class InvalidDocument(KeyError):
	pass

def valid_groups(groups):
	return {name: set(map(Path, paths)) for name, paths in groups.items()}

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

		try:
			lexer = self.tokenizers[path.suffix]
		except KeyError:
			logging.debug("Ignoring %s (invalid suffix)", path)
			return 0

		try:
			doc_id = self.docs2ids[path]
		except KeyError:
			doc_id = self.docs2ids[path] = len(self.docs2ids)
		else:
			if self.ids2docs[doc_id] is not None:
				logging.debug("Ignoring %s (duplicate path)", path)
				return 0

		freqs = lexer.tokenize(path)
		self.ids2docs[doc_id] = path
		if self.keep_docs:
			self.doc_freqs[doc_id] = freqs
		for token, freq in freqs.items():
			self.index[token][doc_id] = freq

		return len(freqs)

	def remove_document(self, path):
		# type: (Path, ) -> None

		""" If `InvertedIndex` was created with `keep_docs=True`,
			the complexity is O(number of unique tokens in document).
			If created with `keep_docs=False`,
			the complexity is O(number of tokens in index)
		"""

		try:
			doc_id = self.docs2ids[path]
			self.ids2docs[doc_id] = None  # keep doc_id for later reuse, but mark as removed
		except KeyError:
			raise InvalidDocument(path)

		if self.keep_docs:
			for token, freq in self.doc_freqs[doc_id].items():
				del self.index[token][doc_id]
		else:
			for token, freqs in self.index.items():
				freqs.pop(doc_id, None)

	def get_docs(self, token):
		# type: (str, ) -> Dict[int, int]

		return self.index.get(token, {})  # get() does not insert key into defaultdict

	def get_paths(self, token):
		# type: (str, ) -> Iterator[Tuple[Path, int]]

		docs = self.get_docs(token)
		paths = ((self.ids2docs[doc_id], freq) for doc_id, freq in docs.items())

		return paths

	def get_paths_op(self, tokens, setop):
		# type: (Sequence[str], Callable[[*Set[int]], Set[int]]) -> Iterator[Tuple[Path, int]]

		freqs = defaultdict(int)

		for token in tokens:
			for doc_id, freq in self.get_docs(token).items():
				freqs[doc_id] += freq

		sets = tuple(set(self.index.get(token, {}).keys()) for token in tokens)
		docs = setop(*sets)
		paths = ((self.ids2docs[doc_id], freqs[doc_id]) for doc_id in docs)

		return paths

class Retriever(object):

	def __init__(self, invindex):
		self.invindex = invindex
		self.groups = {} # type: Dict[str, Set[Path]]

	def _sorted(self, groupname, paths, sortby="path"):
		assert_choice("sortby", sortby, {"path", "freq"})

		grouppaths = list(map(str, self.groups[groupname]))
		paths = ((path, freq) for path, freq in paths if any(fspath(path).startswith(gp) for gp in grouppaths))

		if sortby == "path":
			return sorted(paths, key=itemgetter(0), reverse=False)
		elif sortby == "freq":
			return sorted(paths, key=itemgetter(1), reverse=True)

	def search_token(self, groupname, token, sortby="path"):
		# type: (str, str) -> List[Tuple[Path, int]]

		paths = self.invindex.get_paths(token)
		return self._sorted(groupname, paths, sortby)

	def search_tokens_and(self, groupname, tokens, sortby="path"):
		# type: (str, Sequence[str], str) -> List[Tuple[Path, int]]

		paths = self.invindex.get_paths_op(tokens, set.intersection)
		return self._sorted(groupname, paths, sortby)

	def search_tokens_or(self, groupname, tokens, sortby="path"):
		# type: (str, Sequence[str], str) -> List[Tuple[Path, int]]

		paths = self.invindex.get_paths_op(tokens, set.union)
		return self._sorted(groupname, paths, sortby)

class Indexer(object):

	def __init__(self, invindex):
		self.invindex = invindex
		self.groups = {} # type: Dict[str, Set[Path]]
		self.mtimes = dict() # type: Dict[Path, int]

	def index(self, suffixes=None, partial=True, gitignore=False, progressfunc=None):
		# type: (Set[str], bool, bool, Callable[[str], Any]) -> int

		""" Searches Indexer.paths for indexable files and indexes them.
			Returns the number of files added to the index.
		"""

		if not partial:
			self.invindex.clear()
			self.mtimes = dict()
			add = True
		else:
			touched = set() # type: Set[Path]

		docs_added = 0
		docs_removed = 0

		for path in chain.from_iterable(self.groups.values()):

			if gitignore:
				it = gitignore_iterdir(path)
			else:
				it = path.rglob("*")

			for filename in it:

				if suffixes:
					if filename.suffix not in suffixes:
						continue

				new_mtime = filename.stat().st_mtime_ns
				if partial:
					touched.add(filename)

					try:
						old_mtime = self.mtimes[filename]
					except KeyError:
						add = True
					else:
						if old_mtime == new_mtime:
							add = False
						else:
							try:
								self.invindex.remove_document(filename)
								docs_removed += 1
							except InvalidDocument:
								pass
							add = True

				if add:
					self.mtimes[filename] = new_mtime
					if self.invindex.add_document(filename):
						docs_added += 1
					if progressfunc:
						progressfunc(filename)

		if partial:
			deleted = self.mtimes.keys() - touched
			for filename in deleted:
				self.invindex.remove_document(filename)
				del self.mtimes[filename]
				docs_removed += 1

		return docs_added, docs_removed
