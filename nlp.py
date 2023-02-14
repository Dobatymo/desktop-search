from typing import Any
from typing import Counter as CounterT
from typing import Dict, Iterable, List

import spacy


def str2lower(s):
    return s.lower()


DEFAULT_CONFIG = {
    "code": {
        "tokenize": False,
        "case-sensitive": True,
    },
    "text": {
        "tokenize": True,
        "case-sensitive": False,
        "lemmatize": True,
    },
}


class Preprocess:
    def __init__(self, model: str = "en_core_web_sm") -> None:
        exclude = ["tok2vec", "parser", "ner"]
        self.nlp = spacy.load(model, exclude=exclude)
        assert self.nlp.pipe_names == ["tagger", "attribute_ruler", "lemmatizer"], self.nlp.pipe_names

    def text(self, config: Dict[str, Any], text: str) -> List[str]:
        if config["tokenize"]:
            doc = self.nlp(text)
            if config["case-sensitive"]:
                if config["lemmatize"]:
                    return [tok.lemma_ for tok in doc]
                else:
                    return [tok.text for tok in doc]
            else:
                if config["lemmatize"]:
                    return [tok.lemma_.lower() for tok in doc]
                else:
                    return [tok.lower_ for tok in doc]
        else:
            assert not config.get("lemmatize", False)
            tokens = text.split(" ")
            if config["case-sensitive"]:
                return tokens
            else:
                return list(map(str2lower, tokens))

    def batch(self, config: Dict[str, Any], texts: Iterable[str], freqs: CounterT[str]) -> None:
        # fixme: don't store huge-ass tokens like in `get-pip.py`

        if config["tokenize"]:
            if config["case-sensitive"]:
                if config["lemmatize"]:
                    for doc in self.nlp.pipe(texts):
                        freqs.update(tok.lemma_ for tok in doc)
                else:
                    for doc in self.nlp.pipe(texts):
                        freqs.update(tok.text for tok in doc)
            else:
                if config["lemmatize"]:
                    for doc in self.nlp.pipe(texts):
                        freqs.update(tok.lemma_.lower() for tok in doc)
                else:
                    for doc in self.nlp.pipe(texts):
                        freqs.update(tok.lower_ for tok in doc)
        else:
            assert not config.get("lemmatize", False)
            if config["case-sensitive"]:
                freqs.update(texts)
            else:
                freqs.update(map(str2lower, texts))
