import logging
from collections import defaultdict
from math import log10
from operator import itemgetter
from os import fspath
from pathlib import Path
from typing import Any, Callable, DefaultDict, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union, cast

from genutility.exceptions import assert_choice

from ..utils import CodeAnalyzer, IndexerBase, IndexerError, InvalidDocument, NotAnalyzable, RetrieverBase

OptionalSearchResult = Tuple[Optional[Path], Union[int, float]]
SearchResult = Tuple[Path, Union[int, float]]

OP_METHODS = ("and", "or")
SORTBY_METHODS = frozenset(("path", "score"))
SCORING_METHODS = frozenset(("unscored", "term_freq", "tfidf"))


class InvertedIndexMemory:
    docs2ids: Dict[Path, int]
    ids2docs: Dict[int, Optional[Path]]
    table: Dict[str, Dict[str, Dict[int, int]]]
    doc_freqs: Dict[str, Dict[int, Dict[str, int]]]

    def __getstate__(self):
        state = self.__dict__.copy()
        del state["analyzer"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def set_analyzer(self, analyzer: CodeAnalyzer):
        self.analyzer = analyzer

    def __init__(self, analyzer: CodeAnalyzer, keep_docs: bool = True) -> None:
        """Set `keep_docs=False` to improve memory usage,
        but decrease `remove_document()` performance.
        """

        self.analyzer = analyzer
        self.keep_docs = keep_docs
        self.clear()

    def clear(self) -> None:
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

    def add_document(self, path: Path) -> bool:
        try:
            freqs_dict = self.analyzer.analyze(path)
        except NotAnalyzable:
            return False

        return self.add_document_freqs(path, freqs_dict)

    def add_document_freqs(self, path: Path, freqs_dict: Dict[str, Dict[str, int]]):
        try:
            doc_id = self.docs2ids[path]
        except KeyError:
            doc_id = self.docs2ids[path] = len(self.docs2ids)
        else:
            if self.ids2docs[doc_id] is not None:
                logging.warning("Ignoring %s (duplicate path)", path)
                return False

        self.ids2docs[doc_id] = path

        if self.keep_docs:
            for name, freqs in freqs_dict.items():
                self.doc_freqs[name][doc_id] = freqs

        for name, freqs in freqs_dict.items():
            index = self.table[name]
            for token, freq in freqs.items():
                index[token][doc_id] = freq

        return True

    def remove_document(self, path: Path) -> None:
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
                for token, _freq in field_freqs[doc_id].items():
                    del index[token][doc_id]
        else:
            for _name, index in self.table.items():
                for _token, freqs in index.items():
                    freqs.pop(doc_id, None)

    def get_docs(self, field: str, token: str) -> Dict[int, int]:
        return self.table[field].get(token, {})  # get() does not insert key into defaultdict

    @staticmethod
    def _tfidf(tf: int, idf: float) -> float:
        return tf * idf

    def get_paths(self, field: str, token: str, scoring: str = "unscored") -> Iterable[OptionalSearchResult]:
        assert_choice("scoring", scoring, SCORING_METHODS)

        docs = self.get_docs(field, token)
        paths: Iterable[OptionalSearchResult]

        if scoring == "unscored":
            paths = ((self.ids2docs[doc_id], i) for i, doc_id in enumerate(docs.keys()))
        elif scoring == "term_freq":
            paths = ((self.ids2docs[doc_id], term_freq) for doc_id, term_freq in docs.items())
        elif scoring == "tfidf":
            if docs:
                num_docs = len(self.table[field])
                inv_doc_freq = log10(num_docs / len(docs))

            paths = (
                (self.ids2docs[doc_id], self._tfidf(term_freq, inv_doc_freq)) for doc_id, term_freq in docs.items()
            )

        return paths

    def get_paths_op(
        self, field: str, tokens: Sequence[str], setop: Callable[..., Set[int]], scoring: str = "unscored"
    ) -> Iterable[OptionalSearchResult]:
        assert_choice("scoring", scoring, SCORING_METHODS)

        sets = tuple(set(self.get_docs(field, token).keys()) for token in tokens)
        docs_op = setop(*sets)
        paths: Iterable[OptionalSearchResult]

        if scoring == "unscored":
            paths = ((self.ids2docs[doc_id], i) for i, doc_id in enumerate(docs_op))

        elif scoring == "term_freq":
            term_freqs: DefaultDict[int, int] = defaultdict(int)
            for token in tokens:
                docs = self.get_docs(field, token)
                for doc_id, term_freq in docs.items():
                    term_freqs[doc_id] += term_freq
            paths = ((self.ids2docs[doc_id], term_freqs[doc_id]) for doc_id in docs_op)

        elif scoring == "tfidf":
            tfidf: DefaultDict[int, float] = defaultdict(float)
            for token in tokens:
                docs = self.get_docs(field, token)
                if docs:
                    num_docs = len(self.table[field])
                    inv_doc_freq = log10(num_docs / len(docs))
                for doc_id, term_freq in docs.items():
                    tfidf[doc_id] += self._tfidf(term_freq, inv_doc_freq)

            paths = ((self.ids2docs[doc_id], tfidf[doc_id]) for doc_id in docs_op)

        return paths

    def _memory_usage(self) -> Dict[str, int]:
        from pympler import asizeof

        return {
            "total": asizeof.asizeof(self),
            "docs2ids": asizeof.asizeof(self.docs2ids),
            "ids2docs": asizeof.asizeof(self.ids2docs),
            "table": asizeof.asizeof(self.table),
            "doc_freqs": asizeof.asizeof(self.doc_freqs),
        }


class RetrieverMemory(RetrieverBase):
    def __init__(self, invindex: InvertedIndexMemory) -> None:
        RetrieverBase.__init__(self)
        self.invindex = invindex

    def _sorted(self, groupname: str, paths: Iterable[OptionalSearchResult], sortby="path") -> List[SearchResult]:
        assert_choice("sortby", sortby, SORTBY_METHODS)

        grouppaths = list(map(str, self.groups[groupname]))
        try:
            filtered_paths = cast(
                Iterable[SearchResult],
                (
                    (path, score)
                    for path, score in paths
                    if any(fspath(path).startswith(gp) for gp in grouppaths)  # type: ignore[arg-type]
                ),
            )
        except TypeError as e:
            raise RuntimeError(e)

        if sortby == "path":
            return sorted(filtered_paths, key=itemgetter(0), reverse=False)
        elif sortby == "score":
            return sorted(filtered_paths, key=itemgetter(1), reverse=True)
        else:
            assert False

    def search_token(
        self, groupname: str, field: str, token: str, sortby: str = "path", scoring: str = "unscored"
    ) -> List[SearchResult]:
        paths = self.invindex.get_paths(field, token, scoring)
        return self._sorted(groupname, paths, sortby)

    def search_tokens_and(
        self, groupname: str, field: str, tokens: Sequence[str], sortby: str = "path", scoring: str = "unscored"
    ) -> List[SearchResult]:
        paths = self.invindex.get_paths_op(field, tokens, set.intersection, scoring)
        return self._sorted(groupname, paths, sortby)

    def search_tokens_or(
        self, groupname: str, field: str, tokens: Sequence[str], sortby: str = "path", scoring: str = "unscored"
    ) -> List[SearchResult]:
        paths = self.invindex.get_paths_op(field, tokens, set.union, scoring)
        return self._sorted(groupname, paths, sortby)

    def search_text(
        self, groupname: str, field: str, text: str, op: str, sortby: str = "path", scoring: str = "unscored"
    ) -> List[SearchResult]:
        if op not in OP_METHODS:
            raise ValueError("`op` must be 'and' or 'or'")

        tokens = self.invindex.analyzer.query(field, text)
        if len(tokens) == 1:
            paths = self.search_token(groupname, field, tokens[0], sortby, scoring)
        else:
            if op == "and":
                paths = self.search_tokens_and(groupname, field, tokens, sortby, scoring)
            elif op == "or":
                paths = self.search_tokens_or(groupname, field, tokens, sortby, scoring)

        return paths


class IndexerMemory(IndexerBase):
    def __init__(self, invindex: InvertedIndexMemory):
        IndexerBase.__init__(self)
        self.invindex = invindex

    def index(
        self,
        suffixes: Optional[Set[str]] = None,
        partial: bool = True,
        gitignore: bool = False,
        config: Optional[Dict[str, Any]] = None,
        progressfunc: Optional[Callable[[Path], Any]] = None,
    ) -> Tuple[int, int, int]:
        """Searches Indexer.paths for indexable files and indexes them.
        Returns the number of files added to the index.
        """

        if partial:
            if config is not None and self.invindex.analyzer.config != config:
                raise IndexerError("Changing case-sensitivity requires a full index rebuild")
        else:
            self.invindex.clear()
            self.invindex.analyzer.set_config(config)

        return self._index(suffixes, partial, gitignore, progressfunc)

    def add_document(self, filename: Path) -> bool:
        return self.invindex.add_document(filename)

    def remove_document(self, filename: Path) -> None:
        self.invindex.remove_document(filename)

    def update_document(self, filename: Path) -> bool:
        self.invindex.remove_document(filename)
        return self.invindex.add_document(filename)
