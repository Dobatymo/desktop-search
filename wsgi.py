from __future__ import generator_stop

import logging
import os
import subprocess
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import humanize
from appdirs import user_data_dir
from flask import Flask, abort, flash, make_response, redirect, render_template, request, url_for
from genutility.file import read_file
from genutility.json import read_json
from genutility.pickle import read_pickle, write_pickle
from genutility.time import MeasureTime
from tqdm import tqdm

from utils import Indexer, InvertedIndex, Retriever, valid_groups

app = Flask(__name__)
app.secret_key = os.urandom(24)

APP_NAME = "desktop-search"
APP_AUTHOR = "Dobatymo"

APPDATA = Path(user_data_dir(APP_NAME, APP_AUTHOR))
CONFIG_FILE = "config.json"
INDEX_FILE = "index.p.gz"

DEFAULT_GROUPS = {}  # type: Dict[str, List[str]]
DEFAULT_OPEN = 'edit "{path}"'
DEFAULT_EXTENSIONS = []  # type: List[str]

DEFAULT_CONFIG = {
    "groups": DEFAULT_GROUPS,
    "open": DEFAULT_OPEN,
    "extensions": DEFAULT_EXTENSIONS,
}

appdata_dir = None  # type: Optional[Path]
config = None
invindex = None
indexer = None
retriever = None


def read_config():
    # type: () -> dict

    assert appdata_dir
    try:
        return read_json(appdata_dir / CONFIG_FILE)
    except FileNotFoundError:
        return DEFAULT_CONFIG


def read_index():

    assert appdata_dir
    try:
        indexer = read_pickle(appdata_dir / INDEX_FILE)
        invindex = indexer.invindex
    except FileNotFoundError:
        invindex = InvertedIndex()
        indexer = Indexer(invindex)
        retriever = Retriever(invindex)

    retriever = Retriever(invindex)
    retriever.groups = indexer.groups
    return invindex, indexer, retriever


def shutdown_server():
    func = request.environ.get("werkzeug.server.shutdown")
    if func is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    func()


@app.route("/open/<path:path>", methods=["GET"])
def open_file(path):
    cmd = config.get("open", DEFAULT_OPEN)

    try:
        cmd = cmd.format(path=path)
    except KeyError:
        flash(f"Invalid open command: '{cmd}'", "error")
    else:
        subprocess.run(cmd, shell=True)

    return render_template("back.htm")


@app.route("/view-raw/<path:path>", methods=["GET"])
def view_file(path):
    try:
        text = read_file(path, "rt")
    except FileNotFoundError:
        abort(404)

    response = make_response(text, 200)
    response.mimetype = "text/plain"
    return response


@app.route("/view-html/<path:path>", methods=["GET"])
def view_file_highlight(path):
    try:
        text = read_file(path, "rt")
    except FileNotFoundError:
        abort(404)

    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_for_filename

    lexer = get_lexer_for_filename(path)
    html = highlight(text, lexer, HtmlFormatter())
    return render_template("view-html.htm", html=html)


@app.route("/reindex", methods=["POST"])
def reindex():
    global config
    assert appdata_dir

    partial = bool(request.form.get("partial", False))
    gitignore = bool(request.form.get("gitignore", False))
    config = read_config()
    groups = config.get("groups", DEFAULT_GROUPS)

    if not groups:
        flash("No groups to index found", "warning")
        redirect(url_for("index"))

    _groups = valid_groups(groups)
    indexer.groups = _groups
    retriever.groups = _groups

    suffixes = set(config.get("extensions", DEFAULT_EXTENSIONS))

    with tqdm() as pbar, MeasureTime() as seconds:
        try:
            docs_added, docs_removed = indexer.index(
                suffixes, partial, gitignore, progressfunc=lambda x: pbar.update(1)
            )
        except FileNotFoundError as e:
            flash(f"FileNotFoundError: {e}. Check the config file.", "error")
            redirect(url_for("index"))

        delta = humanize.naturaldelta(timedelta(seconds=seconds.get()))
        flash(
            f"Indexed {docs_added} new documents and removed {docs_removed} old ones in {delta}.",
            "info",
        )

    write_pickle(indexer, appdata_dir / INDEX_FILE, safe=True)

    return redirect(url_for("index"))


@app.route("/statistics", methods=["GET"])
def statistics():

    stats = {
        "files": len(invindex.ids2docs),
        "tokens": len(invindex.index),
        "suffixes": Counter(path.suffix for path in invindex.docs2ids),
    }

    return render_template("statistics.htm", stats=stats)


@app.route("/close-app", methods=["GET"])
def close():
    shutdown_server()
    return render_template("close.htm")


@app.route("/", methods=["GET", "POST"])
def index():

    groupnames = config.get("groups", DEFAULT_GROUPS).keys()

    token = request.form.get("token", "")
    op = request.form.get("op")
    groupname = request.form.get("groupname")

    if token:

        if groupname not in groupnames:
            abort(400)

        tokens = token.split(" ")
        if len(tokens) == 1:
            paths = retriever.search_token(groupname, token)
        else:
            if op == "and":
                paths = retriever.search_tokens_and(groupname, tokens)
            elif op == "or":
                paths = retriever.search_tokens_or(groupname, tokens)
            else:
                abort(400)
    else:
        paths = []

    stats = {
        "files": len(invindex.ids2docs),
        "tokens": len(invindex.index),
    }

    return render_template(
        "index.htm", token=token, paths=paths, stats=stats, groupnames=groupnames
    )


if __name__ == "__main__":

    import webbrowser
    from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

    from genutility.args import is_dir

    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument(
        "-b", "--open-browser", action="store_true", help="Open browser after start"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable more print output"
    )
    parser.add_argument(
        "--appdata", type=is_dir, default=APPDATA, help="Path to appdata directory"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    appdata_dir = args.appdata
    config = read_config()
    invindex, indexer, retriever = read_index()

    if args.open_browser:
        webbrowser.open(f"http://{args.host}:{args.port}/")

    app.run(host=args.host, port=args.port)

else:
    appdata_dir = APPDATA
    config = read_config()
    invindex, indexer, retriever = read_index()
