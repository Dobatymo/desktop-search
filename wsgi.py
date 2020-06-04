from __future__ import absolute_import, division, print_function, unicode_literals

import os

from flask import Flask, render_template, request, flash, redirect, url_for
from genutility.compat.pathlib import Path
from genutility.json import read_json

from utils import InvertedIndex, Indexer

app = Flask(__name__)
app.secret_key = os.urandom(24)

invindex = InvertedIndex()
indexer = Indexer(invindex)

paths = read_json("paths.json")

indexer.add_paths(map(Path, paths))

@app.route("/reindex", methods=["POST"])
def reindex():
	indexer.index()
	flash("Reindexing done!")
	return redirect(url_for("index"))

@app.route("/", methods=["GET", "POST"])
def index():

	token = request.form.get("token")

	if token:
		paths = invindex.search_token(token)
	else:
		paths = []

	return render_template("index.htm", paths=paths)

if __name__ == "__main__":
	app.run(host="localhost", port=8080)
