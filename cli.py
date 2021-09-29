from __future__ import generator_stop

from backend.memory import IndexerMemory, InvertedIndexMemory, RetrieverMemory
from genutility.json import read_json
from tqdm import tqdm

from utils import CodeAnalyzer, valid_groups


def main(groups):

    analyzer = CodeAnalyzer()
    index = InvertedIndexMemory(analyzer)
    indexer = IndexerMemory(index)
    retriever = RetrieverMemory(index)

    _groups = valid_groups(groups)
    indexer.groups = _groups
    retriever.groups = _groups

    with tqdm() as pbar:
        indexer.index(progressfunc=lambda x: pbar.update(1))

    try:
        while True:
            token = input(">")
            for path in index.search_token(token):
                print(path)

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":

    groups = read_json("config.json")["groups"]

    main(groups)
