from __future__ import annotations, generator_stop

import json
import logging
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import timedelta
from os import fspath
from pathlib import Path
from typing import Dict, List, Optional

import humanize
from appdirs import user_data_dir
from flask import Flask, abort, flash, make_response, redirect, render_template, request, url_for
from genutility.file import read_file
from genutility.json import read_json, write_json
from genutility.pickle import read_pickle, write_pickle
from genutility.time import MeasureTime
from jsonschema import ValidationError
from markupsafe import Markup
from tqdm import tqdm

from nlp import DEFAULT_CONFIG as DEFAULT_NLP_CONFIG
from nlp import Preprocess
from utils import Indexer, IndexerError, InvertedIndex, Retriever, valid_groups

app = Flask(__name__)
app.secret_key = os.urandom(24)

APP_NAME = "desktop-search"
APP_AUTHOR = "Dobatymo"

DEFAULT_APPDATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))
CONFIG_FILE = "config.json"
INDEX_FILE = "index.p.gz"

DEFAULT_GROUPS = {}  # type: Dict[str, List[str]]
if platform.system() == "Windows":
    DEFAULT_OPEN = 'notepad "{path}"'
else:
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
    config_path = appdata_dir / CONFIG_FILE
    try:
        return read_json(config_path, schema="config.schema.json")
    except FileNotFoundError:
        return DEFAULT_CONFIG
    except (json.JSONDecodeError, ValidationError) as e:
        logging.critical("Failed to parse config file <%s>: %s", config_path, e)
        sys.exit(1)


def read_index():

    assert appdata_dir
    preprocess = Preprocess()

    try:
        indexer = read_pickle(appdata_dir / INDEX_FILE)
        invindex = indexer.invindex
        invindex.init(preprocess)
    except FileNotFoundError:
        invindex = InvertedIndex(preprocess)
        indexer = Indexer(invindex)

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
        msg = Markup("Invalid open command: <pre>{}</pre>").format(cmd)
        flash(msg, "error")
    else:
        subprocess.run(cmd, shell=True)

    return render_template("back.htm")  # don't redirect but go back in history for better caching


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
    return render_template("view-html.htm", html=Markup(html))


@app.route("/reindex", methods=["POST"])
def reindex():
    global config
    assert appdata_dir

    nlp_config = DEFAULT_NLP_CONFIG

    partial = bool(request.form.get("partial", False))
    gitignore = bool(request.form.get("gitignore", False))
    nlp_config["code"]["case-sensitive"] = bool(request.form.get("case_sensitive_code", True))
    nlp_config["text"]["case-sensitive"] = bool(request.form.get("case_sensitive_text", False))

    config = read_config()
    groups = config.get("groups", DEFAULT_GROUPS)

    if not groups:
        flash("No groups to index found. Please edit config file.", "warning")
        return redirect(url_for("index"))

    _groups = valid_groups(groups)
    indexer.groups = _groups
    retriever.groups = _groups

    suffixes = set(config.get("extensions", DEFAULT_EXTENSIONS))

    with tqdm() as pbar, MeasureTime() as seconds:
        try:
            docs_added, docs_removed = indexer.index(
                suffixes, partial, gitignore, nlp_config, progressfunc=lambda x: pbar.update(1)
            )
        except FileNotFoundError as e:
            msg = Markup("FileNotFoundError: <pre>{}</pre>. Check the config file.").format(e)
            flash(msg, "error")
            return redirect(url_for("index"))
        except IndexerError as e:
            msg = Markup("{}.").format(e)
            flash(msg, "error")
            return redirect(url_for("index"))

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
        "tokens": {k: len(v) for k, v in invindex.table.items()},
        "suffixes": Counter(path.suffix for path in invindex.docs2ids),
    }

    return render_template("statistics.htm", stats=stats)


@app.route("/open-config", methods=["GET"])
def open_config():
    global config
    assert appdata_dir

    config_path = fspath(appdata_dir / CONFIG_FILE)
    try:
        config = read_json(config_path, schema="config.schema.json")
    except (json.JSONDecodeError, ValidationError) as e:
        config_str = read_file(config_path, "rt")
        msg = Markup("Failed to parse config file: <pre>{}</pre>").format(e)
        flash(msg, "error")
        return render_template("config.htm", config_str=config_str, config_path=config_path)
    except FileNotFoundError:
        config = DEFAULT_CONFIG
        flash("Default config loaded", "info")
        write_json(config, config_path, indent="\t")
    else:
        flash("Config reloaded", "info")

    config_str = json.dumps(config, indent="\t")

    cmd = config.get("open", DEFAULT_OPEN)

    try:
        cmd = cmd.format(path=config_path)
    except KeyError:
        msg = Markup("Invalid open command: <pre>{}</pre>").format(cmd)
        flash(msg, "error")
        return render_template("config.htm", config=config_str)

    try:
        proc = subprocess.run(cmd, shell=True)
        proc.check_returncode()
    except subprocess.CalledProcessError as e:
        msg = Markup("Failed to open config file: <pre>{}</pre>").format(e)
        flash(msg, "error")
        return render_template("config.htm", config_str=config_str, config_path=config_path)

    return redirect(url_for("index"))


@app.route("/close-app", methods=["GET"])
def close():
    shutdown_server()
    return render_template("close.htm")


@app.route("/", methods=["GET", "POST"])
def index():

    groupnames = config.get("groups", DEFAULT_GROUPS).keys()

    if not groupnames:
        flash("No groups to index found. Please edit config file.", "warning")

    groupname = request.form.get("groupname")
    field = request.form.get("field")
    text = request.form.get("text", "")
    op = request.form.get("op")
    sortby = request.form.get("sortby")

    if text:

        if groupname not in groupnames:
            abort(400)
        if field not in ("code", "text"):
            abort(400)
        if op not in ("and", "or"):
            abort(400)
        if sortby not in ("path", "freq"):
            abort(400)

        paths = retriever.search_text(groupname, field, text, op, sortby)
    else:
        paths = []

    stats = {
        "files": len(invindex.ids2docs),
        "tokens": sum(map(len, invindex.table.values())),
    }

    return render_template(
        "index.htm",
        text=text,
        paths=paths,
        stats=stats,
        groupnames=groupnames,
        config=invindex.config,
    )


if __name__ == "__main__":

    import webbrowser
    from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

    from genutility.args import is_dir

    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("-b", "--open-browser", action="store_true", help="Open browser after start")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable more print output")
    parser.add_argument("--appdata-dir", type=is_dir, default=DEFAULT_APPDATA_DIR, help="Path to appdata directory")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    appdata_dir = args.appdata_dir
    config = read_config()
    invindex, indexer, retriever = read_index()

    if args.open_browser:
        webbrowser.open(f"http://{args.host}:{args.port}/")

    app.run(host=args.host, port=args.port)

else:
    appdata_dir = DEFAULT_APPDATA_DIR
    config = read_config()
    invindex, indexer, retriever = read_index()
