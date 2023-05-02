from os import fspath
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Set, Tuple, Union

from whoosh import writing
from whoosh.fields import ID, NUMERIC, TEXT, Schema
from whoosh.filedb.filestore import FileStorage
from whoosh.qparser import QueryParser
from whoosh.query import And, Or, Term

from utils import IndexerBase, RetrieverBase

SearchResult = Tuple[Path, Union[int, float, None]]


class WhooshIndex:
    schema = Schema(
        path=ID(stored=True, unique=True),
        mtime=NUMERIC(numtype=int, bits=64, stored=True),
        code=TEXT(stored=False, phrase=False),
        text=TEXT(stored=False, phrase=False),
    )

    def __init__(self, path: Path):
        storage = FileStorage(fspath(path))

        if path.exists():
            self.ix = storage.open_index()
        else:
            path.mkdir(exist_ok=True, parents=True)
            self.ix = storage.create_index(self.schema)


class RetrieverWhoosh(RetrieverBase):
    def __init__(self, invindex: WhooshIndex) -> None:
        RetrieverBase.__init__(self)
        self.invindex = invindex

    def searcher(self):
        return self.invindex.ix.searcher()

    def search_text(
        self, groupname: str, field: str, text: str, op: str, sortby: str = "path", scoring: str = "unscored"
    ) -> Iterable[SearchResult]:
        assert sortby in ("path", "score")
        assert scoring in ("unscored", "bm25f")
        scored = scoring != "unscored"
        sortedby = {"score": None}.get(sortby, sortby)
        limit = None

        qp = QueryParser(field, self.invindex.ix.schema)
        q = qp.parse(text)
        terms = list(Term(fieldname, value) for fieldname, value in q.iter_all_terms())

        if op == "and":
            query = And(terms)
        elif op == "or":
            query = Or(terms)

        with self.searcher() as searcher:
            for hit in searcher.search(query, limit=limit, scored=scored, sortedby=sortedby):
                yield Path(hit["path"]), hit.score  # hit.pos, hit.rank, hit.docnum


class IndexerWhoosh(IndexerBase):
    def __init__(self, invindex: WhooshIndex):
        IndexerBase.__init__(self)

        self.invindex = invindex
        self.writer: Optional[writing.IndexWriter] = None

    def getwriter(self):
        return self.invindex.ix.writer()

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

        with self.getwriter() as self.writer:
            if not partial:
                # Using mergetype=CLEAR clears all existing segments so the index will
                # only have any documents you've added to this writer
                self.writer.mergetype = writing.CLEAR

            ret = self._index(suffixes, partial, gitignore, progressfunc)

        return ret

    def _read(self, path: Path) -> Tuple[str, str]:
        with open(path, encoding="utf-8") as fr:
            data = fr.read()

        return data, data

    def add_document(self, path: Path) -> bool:
        code, text = self._read(path)
        assert self.writer
        self.writer.add_document(path=path, code=code, text=text)
        return True

    def remove_document(self, path: Path) -> None:
        assert self.writer
        self.writer.delete_by_term(path=path)

    def update_document(self, path: Path) -> bool:
        code, text = self._read(path)
        assert self.writer
        self.writer.update_document(path=fspath(path), code=code, text=text)
        return True

    def add_documents(self, paths: Iterable[Path]):
        with self.getwriter() as self.writer:
            for path in paths:
                self.add_document(path)

    def update_documents(self, paths: Iterable[Path]):
        with self.getwriter() as self.writer:
            for path in paths:
                self.update_document(path)


if __name__ == "__main__":
    whooshindex = WhooshIndex(Path("indexdir"))
    retriever = RetrieverWhoosh(whooshindex)
    indexer = IndexerWhoosh(whooshindex)

    indexer.update_documents(
        [
            Path("backends/memory.py"),
            Path("backends/whooshdb.py"),
        ]
    )

    for doc in retriever.search_text("", "code", "IndexerWhoosh", "and", "path", "bm25f"):
        print(doc)

    print("---")

    for doc in retriever.search_text("", "code", "add_document", "and", "path", "unscored"):
        print(doc)

    print("---")

    for doc in retriever.search_text("", "code", "add_document", "and", "score", "bm25f"):
        print(doc)
