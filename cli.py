from __future__ import absolute_import, division, print_function, unicode_literals

from tqdm import tqdm
from genutility.compat.pathlib import Path
from genutility.json import read_json

from utils import InvertedIndex, Indexer

def main(paths):

	index = InvertedIndex()
	indexer = Indexer(index)

	indexer.add_paths(map(Path, paths))

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

	paths = read_json("paths.json")

	main(paths)
