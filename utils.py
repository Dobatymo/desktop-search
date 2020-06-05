from __future__ import absolute_import, division, print_function, unicode_literals

import logging, tokenize
from collections import defaultdict, Counter
from operator import itemgetter
from typing import TYPE_CHECKING

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

if TYPE_CHECKING:
	from typing import Iterator
	from genutility.compat.pathlib import Path

def tokenize_python(path):
	# type: (str, ) -> Iterator[str]

	with tokenize.open(path) as fr:
		for type, string, start, end, line in tokenize.generate_tokens(fr.readline):
			if type == tokenize.NAME:
				yield string

def _gitignore_iterdir(path, spec):

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
	spec = PathSpec(map(GitWildMatchPattern, defaultignore))
	return _gitignore_iterdir(path, spec)

class InvertedIndex(object):

	def __init__(self):
		self.docs2ids = {}
		self.ids2docs = {}
		self.index = defaultdict(list)

	def add_document(self, path):
		# type: (Path, ) -> int

		freqs = Counter()

		if path.suffix == ".py":
			doc_id = self.docs2ids.setdefault(path, len(self.docs2ids))
			self.ids2docs[doc_id] = path

			try:
				freqs.update(tokenize_python(path))
				for token, freq in freqs.items():
					self.index[token].append((doc_id, freq))
			except IndentationError as e:
				logging.warning("IndentationError in %s: %s", path, e)
			except tokenize.TokenError as e:
				logging.warning("TokenError in %s: %s", path, e)

		# ".js" pip install pyjsparser

		else:
			logging.debug("Ignoring %s", path)

		return len(freqs)

	def search_token(self, token, sortby="path"):

		if sortby not in {"path", "freq"}:
			raise ValueError(sortby)

		try:
			docs = self.index[token]
		except KeyError:
			return []

		if sortby == "path":
			return sorted(self.ids2docs[doc_id] for doc_id, freq in docs)
		elif sortby == "freq":
			return [self.ids2docs[doc_id] for doc_id, freq in sorted(docs, key=itemgetter(1), reverse=True)]
		else:
			assert False

class Indexer(object):

	def __init__(self, invindex):
		self.invindex = invindex
		self.paths = []

	def add_path(self, path):
		self.paths.append(path)

	def add_paths(self, paths):
		for path in paths:
			self.paths.append(path)

	def index(self, gitignore=False, progressfunc=None):
		# type: (bool, Callable[[str], Any]) -> None

		for path in self.paths:
		
			if gitignore:
				it = gitignore_iterdir(path)
			else:
				it = path.rglob("*")
		
			for filename in it:
				self.invindex.add_document(filename)
				if progressfunc:
					progressfunc(filename)
