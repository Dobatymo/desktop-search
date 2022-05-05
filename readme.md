# Desktop search

Simple app to search the contents of local files. At the moment only python files are supported.

## Install and run
- Install Python 3.7 or higher.
- `py -m pip install -r requirements.txt` (Windows) / `python3 -m pip install -r requirements.txt` (Linux)
- `py -m spacy download en_core_web_sm`
- Create a config file based on `examples/config.json.example` and save as `config.json`.
- Run `py -3 wsgi.py` (Windows) / `python3 wsgi.py` (Linux)
- Open <http://localhost:8080/> in your browser to index and search your files.

## Purpose

Only matches full names. For example a search for `itertools` returns all files where `itertools` is imported, but not files where it is mentioned in comments.
Searching itself is super fast. The indexing step is around 5000 files per minute on my computer. It was written mostly to support refactoring when functions are renamed and other source files have to be adjusted.

## Dev
- ctags could be used instead of manual lexing and tag extraction
- trigram index could be used for non-full-word/partial matching

## Todo
- search comments (with select natural language)
- add more tokenizers

## Optional dependenices
- `pip install future-fstrings` to handle files which specifiy `coding: future_fstrings`
