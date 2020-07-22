from __future__ import absolute_import, division, print_function, unicode_literals

import os, subprocess, logging
from datetime import timedelta
from collections import Counter

import humanize
from tqdm import tqdm
from flask import Flask, render_template, request, flash, redirect, url_for, abort
from genutility.compat.pathlib import Path
from genutility.json import read_json
from genutility.time import MeasureTime
from genutility.pickle import read_pickle, write_pickle

from utils import InvertedIndex, Indexer

app = Flask(__name__)
app.secret_key = os.urandom(24)

DEFAULT_CONFIG_FILE = "config.json"
DEFAULT_INDEX_FILE = "index.p"
DEFAULT_PATHS = []
DEFAULT_OPEN = "edit \"{path}\""
DEFAULT_EXTENSIONS = []

DEFAULT_CONFIG = {
	"index-file": DEFAULT_INDEX_FILE,
	"paths": DEFAULT_PATHS,
	"open": DEFAULT_OPEN,
	"extensions": DEFAULT_EXTENSIONS,
}

config_file = None
config = None
invindex = None
indexer = None

def read_config():
	# type: () -> dict

	try:
		return read_json(config_file)
	except FileNotFoundError:
		return DEFAULT_CONFIG

def read_index():

	index_file = config.get("index-file", DEFAULT_INDEX_FILE)
	try:
		indexer = read_pickle(index_file)
		invindex = indexer.invindex
	except FileNotFoundError:
		invindex = InvertedIndex()
		indexer = Indexer(invindex)
	
	return invindex, indexer

@app.route("/open/<path:path>", methods=["GET"])
def open_file(path):
	cmd = config.get("open", DEFAULT_OPEN)

	try:
		cmd = cmd.format(path=path)
	except KeyError:
		flash("Invalid open command: '{}'".format(cmd), "error")
	else:
		subprocess.run(cmd, shell=True)

	return render_template("back.htm")

@app.route("/reindex", methods=["POST"])
def reindex():
	global config

	partial = bool(request.form.get("partial", False))
	gitignore = bool(request.form.get("gitignore", False))
	config = read_config()
	paths = config.get("paths", DEFAULT_PATHS)

	if not paths:
		flash("No paths to index found", "warning")
		redirect(url_for("index"))

	indexer.paths = list(map(Path, paths))
	suffixes = set(config.get("extensions", DEFAULT_EXTENSIONS))
	index_file = config.get("index-file", DEFAULT_INDEX_FILE)

	with tqdm() as pbar, MeasureTime() as seconds:
		docs_added, docs_removed = indexer.index(suffixes, partial, gitignore, progressfunc=lambda x: pbar.update(1))

		delta = humanize.naturaldelta(timedelta(seconds=seconds.get()))
		flash("Indexed {} new documents and removed {} old ones in {}.".format(docs_added, docs_removed, delta), "info")

	write_pickle(indexer, index_file, safe=True)

	return redirect(url_for("index"))

@app.route("/statistics", methods=["GET"])
def statistics():

	stats = {
		"files": len(invindex.ids2docs),
		"tokens": len(invindex.index),
		"suffixes": Counter(path.suffix for path in invindex.docs2ids),
	}

	return render_template("statistics.htm", stats=stats)

@app.route("/", methods=["GET", "POST"])
def index():

	token = request.form.get("token", "")
	op = request.form.get("op")

	if token:

		tokens = token.split(" ")
		if len(tokens) == 1:
			paths = invindex.search_token(token)
		else:
			if op == "and":
				paths = invindex.search_tokens_and(tokens)
			elif op == "or":
				paths = invindex.search_tokens_or(tokens)
			else:
				abort(400)
	else:
		paths = []

	stats = {
		"files": len(invindex.ids2docs),
		"tokens": len(invindex.index),
	}

	return render_template("index.htm", token=token, paths=paths, stats=stats)

if __name__ == "__main__":

	from argparse import ArgumentParser
	import webbrowser
	from genutility.args import is_file

	parser = ArgumentParser()
	parser.add_argument("--host", default="localhost", help="Server host")
	parser.add_argument("--port", type=int, default=8080, help="Server port")
	parser.add_argument("-b", "--open-browser", action="store_true", help="Open browser after start")
	parser.add_argument("-v", "--verbose", action="store_true", help="Enable more print output")
	parser.add_argument("--config", type=is_file, default=DEFAULT_CONFIG_FILE, help="Path to config file")
	args = parser.parse_args()

	if args.verbose:
		logging.basicConfig(level=logging.DEBUG)
	else:
		logging.basicConfig(level=logging.INFO)

	config_file = args.config
	config = read_config()
	invindex, indexer = read_index()

	if args.open_browser:
		webbrowser.open("http://{}:{}/".format(args.host, args.port))

	app.run(host=args.host, port=args.port)

else:
	config_file = DEFAULT_CONFIG_FILE
	config = read_config()
	invindex, indexer = read_index()
