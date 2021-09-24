from __future__ import annotations, generator_stop

import logging
from collections import defaultdict
from importlib import import_module
from itertools import chain
from operator import itemgetter
from os import fspath
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from genutility.exceptions import assert_choice
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

from nlp import DEFAULT_CONFIG, Preprocess

if TYPE_CHECKING:
    from pathspec import Patterns

    from plugin import TokenizerPlugin


class InvalidDocument(KeyError):
    pass


class IndexerError(Exception):
    pass


def valid_groups(groups):
    # type: (Dict[str, List[str]], ) -> Dict[str, Set[Path]]

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

    config: Dict[str, Any]
    docs2ids: Dict[Path, int]
    ids2docs: Dict[int, Optional[Path]]
    table: Dict[str, Dict[str, Dict[int, int]]]
    doc_freqs: Dict[str, Dict[int, Dict[str, int]]]

    def __getstate__(self):
        state = self.__dict__.copy()
        del state["preprocess"]
        del state["tokenizers"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def init(self, preprocess: Preprocess):
        self.preprocess = preprocess
        self.tokenizers = self._get_tokenizers(preprocess, self.config)

    def __init__(self, preprocess: Preprocess, keep_docs: bool = True, config: Optional[Dict[str, Any]] = None) -> None:

        """Set `keep_docs=False` to improve memory usage,
        but decrease `remove_document()` performance.
        """

        self.preprocess = preprocess
        self.keep_docs = keep_docs
        self.clear(config)

    @classmethod
    def _get_tokenizers(
        cls, preprocess: Preprocess, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, TokenizerPlugin]:

        tokenizers = {}  # type: Dict[str, TokenizerPlugin]

        for modname, clsname in cls.lexers.items():
            try:
                module = import_module("plugins.{}".format(modname))
            except ImportError as e:
                logging.warning("Could not import %s: %s", modname, e)
                continue

            obj = getattr(module, clsname)(preprocess, config)
            for suffix in obj.suffixes:
                try:
                    obj = tokenizers[suffix]
                    logging.warning("%s already handled by plugins/%s", suffix, modname)
                except KeyError:
                    tokenizers[suffix] = obj

        return tokenizers

    def clear(self, config: Optional[Dict[str, Any]] = None) -> None:

        self.tokenizers = self._get_tokenizers(self.preprocess, config)
        logging.info("Found lexers for: [%s]", ", ".join(self.tokenizers.keys()))

        self.docs2ids = {}
        self.ids2docs = {}
        self.table = {
            "code": defaultdict(dict),
            "text": defaultdict(dict),
        }
        self.doc_freqs = {
            "code": {},
            "text": {},
        }
        self.config = config or DEFAULT_CONFIG

    def add_document(self, path):
        # type: (Path, ) -> bool

        try:
            lexer = self.tokenizers[path.suffix]
        except KeyError:
            logging.debug("Ignoring %s (invalid suffix)", path)
            return False

        try:
            doc_id = self.docs2ids[path]
        except KeyError:
            doc_id = self.docs2ids[path] = len(self.docs2ids)
        else:
            if self.ids2docs[doc_id] is not None:
                logging.debug("Ignoring %s (duplicate path)", path)
                return False

        freqs_dict = lexer.tokenize(path)
        self.ids2docs[doc_id] = path

        if self.keep_docs:
            for name, freqs in freqs_dict.items():
                self.doc_freqs[name][doc_id] = freqs

        for name, freqs in freqs_dict.items():
            index = self.table[name]
            for token, freq in freqs.items():
                index[token][doc_id] = freq

        return True

    def remove_document(self, path):
        # type: (Path, ) -> None

        """If `InvertedIndex` was created with `keep_docs=True`,
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
            for name, field_freqs in self.doc_freqs.items():
                index = self.table[name]
                for token, freq in field_freqs[doc_id].items():
                    del index[token][doc_id]
        else:
            for name, index in self.table.items():
                for token, freqs in index.items():
                    freqs.pop(doc_id, None)

    def get_docs(self, field: str, token: str) -> Dict[int, int]:

        if not self.config[field]["case-sensitive"]:
            token = token.lower()

        return self.table[field].get(token, {})  # get() does not insert key into defaultdict

    def get_paths(self, field: str, token: str) -> Iterable[Tuple[Optional[Path], int]]:

        docs = self.get_docs(field, token)
        paths = ((self.ids2docs[doc_id], freq) for doc_id, freq in docs.items())

        return paths

    def get_paths_op(
        self, field: str, tokens: Sequence[str], setop: Callable[..., Set[int]]
    ) -> Iterable[Tuple[Optional[Path], int]]:

        freqs = defaultdict(int)  # type: DefaultDict[int, int]

        for token in tokens:
            for doc_id, freq in self.get_docs(field, token).items():
                freqs[doc_id] += freq

        sets = tuple(set(self.get_docs(field, token).keys()) for token in tokens)
        docs = setop(*sets)
        paths = ((self.ids2docs[doc_id], freqs[doc_id]) for doc_id in docs)

        return paths


class Retriever(object):
    def __init__(self, invindex: InvertedIndex) -> None:
        self.invindex = invindex
        self.groups: Dict[str, Set[Path]] = {}

    def _sorted(self, groupname, paths, sortby="path"):
        assert_choice("sortby", sortby, {"path", "freq"})

        grouppaths = list(map(str, self.groups[groupname]))
        paths = ((path, freq) for path, freq in paths if any(fspath(path).startswith(gp) for gp in grouppaths))

        if sortby == "path":
            return sorted(paths, key=itemgetter(0), reverse=False)
        elif sortby == "freq":
            return sorted(paths, key=itemgetter(1), reverse=True)

    def search_token(self, groupname: str, field: str, token: str, sortby: str = "path") -> List[Tuple[Path, int]]:

        paths = self.invindex.get_paths(field, token)
        return self._sorted(groupname, paths, sortby)

    def search_tokens_and(
        self, groupname: str, field: str, tokens: Sequence[str], sortby: str = "path"
    ) -> List[Tuple[Path, int]]:

        paths = self.invindex.get_paths_op(field, tokens, set.intersection)
        return self._sorted(groupname, paths, sortby)

    def search_tokens_or(
        self, groupname: str, field: str, tokens: Sequence[str], sortby: str = "path"
    ) -> List[Tuple[Path, int]]:

        paths = self.invindex.get_paths_op(field, tokens, set.union)
        return self._sorted(groupname, paths, sortby)

    def search_text(self, groupname, field, text, op, sortby):

        if op not in ("and", "or"):
            raise ValueError("`op` must be 'and' or 'or'")

        tokens = self.invindex.preprocess.text(self.invindex.config[field], text)
        if len(tokens) == 1:
            paths = self.search_token(groupname, field, tokens[0], sortby)
        else:
            if op == "and":
                paths = self.search_tokens_and(groupname, field, tokens, sortby)
            elif op == "or":
                paths = self.search_tokens_or(groupname, field, tokens, sortby)

        return paths


class Indexer(object):
    def __init__(self, invindex):
        self.invindex = invindex
        self.groups = {}  # type: Dict[str, Set[Path]]
        self.mtimes = dict()  # type: Dict[Path, int]

    def index(
        self,
        suffixes: Set[str] = None,
        partial: bool = True,
        gitignore: bool = False,
        config: Optional[Dict[str, Any]] = None,
        progressfunc: Callable[[Path], Any] = None,
    ) -> Tuple[int, int]:

        """Searches Indexer.paths for indexable files and indexes them.
        Returns the number of files added to the index.
        """

        if not partial:
            self.invindex.clear(config)
            self.mtimes = dict()
            add = True
        else:
            if self.invindex.config != config:
                raise IndexerError("Changing case-sensitivity requires a full index rebuild")
            touched = set()  # type: Set[Path]

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
