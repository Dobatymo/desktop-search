from backend.memory import IndexerMemory, InvertedIndexMemory, RetrieverMemory
from genutility.json import read_json
from genutility.rich import Progress
from rich.progress import Progress as RichProgress
from utils import CodeAnalyzer, valid_groups


def main(groups) -> None:
    analyzer = CodeAnalyzer()
    index = InvertedIndexMemory(analyzer)
    indexer = IndexerMemory(index)
    retriever = RetrieverMemory(index)

    _groups = valid_groups(groups)
    indexer.groups = _groups
    retriever.groups = _groups

    with RichProgress() as progress:
        p = Progress(progress)
        with p.task(description="Indexing...") as task:
            indexer.index(progressfunc=lambda _: task.advance(1))

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
