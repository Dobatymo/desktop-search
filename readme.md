# Desktop search

Simple app to search the contents of local files. At the moment only python files are supported.

## Install and run

- Install Python 3.8 or higher.
- Create a config file based on `examples/config.json.example` and save as `config.json`.

### Windows

```batch
py -m pip install poetry
py -m poetry install
py -m poetry run python -m spacy download en_core_web_sm
```

### Linux

```shell
python3 -m pip install poetry
python3 -m poetry install
python3 -m poetry run python -m spacy download en_core_web_sm
```

### Run
- Run `py -m poetry run python wsgi.py -b` (Windows) / `poetry run python wsgi.py -b` (Linux)
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
- index files in archives like zip files

## Optional dependencies
- `pip install future-fstrings` to handle files which specify `coding: future_fstrings`
