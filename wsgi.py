from __future__ import absolute_import, division, print_function, unicode_literals

import os, subprocess
from datetime import timedelta

import humanize
from tqdm import tqdm
from flask import Flask, render_template, request, flash, redirect, url_for
from genutility.compat.pathlib import Path
from genutility.json import read_json
from genutility.time import MeasureTime
from genutility.pickle import read_pickle, write_pickle

from utils import InvertedIndex, Indexer

app = Flask(__name__)
app.secret_key = os.urandom(24)

DEFAULT_INDEX_FILE = "index.p"
DEFAULT_PATHS = []
DEFAULT_OPEN = "edit \"{path}\""

DEFAULT_CONFIG = {
	"index-file": DEFAULT_INDEX_FILE,
	"paths": DEFAULT_PATHS,
	"open": DEFAULT_OPEN,
}

def read_config():
	# type: () -> dict

	try:
		return read_json("config.json")
	except FileNotFoundError:
		return DEFAULT_CONFIG

config = read_config()

try:
	invindex = read_pickle(config.get("index-file", DEFAULT_INDEX_FILE))
except FileNotFoundError:
	invindex = InvertedIndex()

indexer = Indexer(invindex)

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

	gitignore = bool(request.form.get("gitignore", False))
	config = read_config()
	paths = config.get("paths", DEFAULT_PATHS)

	if not paths:
		flash("No paths to index found", "warning")
		redirect(url_for("index"))

	indexer.paths = list(map(Path, paths))

	with tqdm() as pbar, MeasureTime() as seconds:
		docs = indexer.index(gitignore=gitignore, progressfunc=lambda x: pbar.update(1))

		delta = humanize.naturaldelta(timedelta(seconds=seconds.get()))
		flash("Indexed {} documents in {}.".format(docs, delta), "info")

		index_file = config.get("index-file", DEFAULT_INDEX_FILE)
		write_pickle(indexer.invindex, index_file)

	return redirect(url_for("index"))

@app.route("/", methods=["GET", "POST"])
def index():

	token = request.form.get("token")

	if token:
		paths = invindex.search_token(token)
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

	parser = ArgumentParser()
	parser.add_argument("--host", default="localhost")
	parser.add_argument("--port", default=8080)
	parser.add_argument("-b", "--open-browser", action="store_true")
	args = parser.parse_args()

	if args.open_browser:
		webbrowser.open("http://{}:{}/".format(args.host, args.port))

	app.run(host=args.host, port=args.port)
