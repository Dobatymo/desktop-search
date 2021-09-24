from __future__ import annotations, generator_stop

import logging
from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any
from typing import Counter as CounterT
from typing import DefaultDict, Dict, Iterator, List, Optional, Tuple, Type

from nlp import DEFAULT_CONFIG

if TYPE_CHECKING:
    from pathlib import Path

    from nlp import Preprocess


class NoLexerFound(Exception):
    pass


class TokenizerPlugin(object):

    exceptions: Dict[Type[Exception], str]

    def __init__(self, preprocess: Preprocess, config: Optional[Dict[str, Any]] = None):

        self.preprocess = preprocess
        self.config = config or DEFAULT_CONFIG

    def _tokenize(self, path: Path) -> Iterator[Tuple[str, str]]:

        raise NotImplementedError

    def tokenize(self, path: Path) -> Dict[str, CounterT[str]]:

        tokens: DefaultDict[str, List[str]] = defaultdict(list)

        try:
            for field, token in self._tokenize(path):
                tokens[field].append(token)
        except Exception as e:
            for exc, tpl in self.exceptions.items():
                if isinstance(e, exc):
                    logging.warning(tpl.format(path=path, exc=e))
                    break
            else:
                raise

        freqs: Dict[str, CounterT[str]] = {}

        for field, fieldconfig in self.config.items():
            freqs[field] = Counter()
            try:
                self.preprocess.batch(fieldconfig, tokens[field], freqs[field])
            except ValueError as e:
                logging.error("Preprocessing <%s> [%s] failed: %s", path, field, e)

        return freqs
