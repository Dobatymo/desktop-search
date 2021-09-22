from __future__ import generator_stop

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

    def __init__(self, case_sensitive: bool = True):
        self.case_sensitive = case_sensitive

    def _tokenize(self, path):
        # type: (Path, ) -> Iterator[str]

        raise NotImplementedError

    def tokenize(self, path):
        # type: (Path, ) -> Counter

        c = Counter()  # type: CounterT[str]

        try:
            if self.case_sensitive:
                c.update(self._tokenize(path))
            else:
                c.update(token.lower() for token in self._tokenize(path))

        except Exception as e:
            for exc, tpl in self.exceptions.items():
                if isinstance(e, exc):
                    logging.warning(tpl.format(path=path, exc=e))
                    break
            else:
                raise

        return c
