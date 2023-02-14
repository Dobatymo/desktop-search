import logging
from importlib import import_module
from itertools import chain
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

from nlp import DEFAULT_CONFIG, Preprocess
from plugin import TokenizerPlugin


class InvalidDocument(KeyError):
    pass


class IndexerError(Exception):
    pass


def valid_groups(groups: Dict[str, List[str]]) -> Dict[str, Set[Path]]:
    return {name: set(map(Path, paths)) for name, paths in groups.items()}


def _gitignore_iterdir(path: Path, spec: PathSpec) -> Iterator[Path]:
    try:
        with (path / ".gitignore").open("r", encoding="utf-8") as fr:
            patterns = list(fr)

        spec = spec + PathSpec(map(GitWildMatchPattern, patterns))

    except FileNotFoundError:
        pass

    for item in path.iterdir():
        if not spec.match_file(item):
            if item.is_file():
                yield item
            elif item.is_dir():
                yield from _gitignore_iterdir(item, spec)


def gitignore_iterdir(path: Path, defaultignore: Sequence[str] = [".git"]) -> Iterator[Path]:
    spec = PathSpec(map(GitWildMatchPattern, defaultignore))
    return _gitignore_iterdir(path, spec)


class NotAnalyzable(Exception):
    pass


class CodeAnalyzer:
    lexers = {
        "calmjs": "CalmjsPlugin",
        "plaintext": "PlaintextPlugin",
        "python": "PythonPlugin",
        "pygments": "PygmentsPlugin",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or DEFAULT_CONFIG
        self.preprocess = Preprocess()
        self.set_config(config)

    @classmethod
    def _get_tokenizers(
        cls, preprocess: Preprocess, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, TokenizerPlugin]:
        tokenizers: Dict[str, TokenizerPlugin] = {}

        for modname, clsname in cls.lexers.items():
            try:
                module = import_module(f"plugins.{modname}")
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

    def set_config(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config
        self.tokenizers = self._get_tokenizers(self.preprocess, config)

    def analyze(self, path: Path) -> Dict[str, Dict[str, int]]:
        try:
            lexer = self.tokenizers[path.suffix]
        except KeyError:
            logging.debug("Ignoring %s (invalid suffix)", path)
            raise NotAnalyzable()

        return lexer.tokenize(path)

    def query(self, field, query: str) -> List[str]:
        return self.preprocess.text(self.config[field], query)


class RetrieverBase:
    def __init__(self):
        self.groups: Dict[str, Set[Path]] = {}

    def set_groups(self, groups: Dict[str, Set[Path]]):
        self.groups = groups


class IndexerBase:
    def __init__(self):
        self.groups: Dict[str, Set[Path]] = {}
        self.mtimes: Dict[Path, int] = {}

    def set_groups(self, groups: Dict[str, Set[Path]]):
        self.groups = groups

    def _index(
        self,
        suffixes: Set[str] = None,
        partial: bool = True,
        gitignore: bool = False,
        progressfunc: Callable[[Path], Any] = None,
    ) -> Tuple[int, int, int]:
        if partial:
            touched: Set[Path] = set()
        else:
            self.mtimes = dict()
            add = True

        docs_added = 0
        docs_removed = 0
        docs_updated = 0

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
                                if self.update_document(filename):
                                    docs_updated += 1
                                else:
                                    docs_removed += 1
                            except InvalidDocument:
                                pass
                            add = False

                if add:
                    self.mtimes[filename] = new_mtime
                    if self.add_document(filename):
                        docs_added += 1
                    if progressfunc:
                        progressfunc(filename)

        if partial:
            deleted = self.mtimes.keys() - touched
            for filename in deleted:
                self.remove_document(filename)
                del self.mtimes[filename]
                docs_removed += 1

        return docs_added, docs_removed, docs_updated

    def add_document(self, filename: Path) -> bool:
        raise NotImplementedError

    def remove_document(self, filename: Path) -> None:
        raise NotImplementedError

    def update_document(self, filename: Path) -> bool:
        raise NotImplementedError
