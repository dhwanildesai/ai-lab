"""Things that choose a tool. The two lexical ones are simulated stand-ins, NOT language models."""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from .registry import Tool


class Selector(Protocol):
    def select(self, query: str, tools: Sequence[Tool]) -> str | None: ...


def tokens(text: str) -> list[str]:
    """Lowercase, split snake_case, drop a trailing plural `s`. Deliberately crude."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words]


class _Lexical:
    def select(self, query: str, tools: Sequence[Tool]) -> str | None:
        docs = [tokens(f"{t.name} {t.description}") for t in tools]
        if not docs:
            return None
        mean_len = sum(map(len, docs)) / len(docs)
        df = Counter(word for doc in docs for word in set(doc))
        idf = {w: math.log(1 + (len(docs) - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        wanted = sorted(set(tokens(query)) & set(idf))
        # Rounding keeps float noise from breaking ties; ties go to the lowest name so that
        # registry order is not a hidden variable.
        ranked = sorted(
            (-round(sum(idf[w] * self._tf(w, doc, mean_len) for w in wanted), 9), tool.name)
            for doc, tool in zip(docs, tools)
        )
        score, name = ranked[0]
        return name if score < 0 else None  # no overlap at all: abstain

    def _tf(self, word: str, doc: list[str], mean_len: float) -> float:
        raise NotImplementedError


class BM25Selector(_Lexical):
    """Order-blind: standard BM25 over name + description."""

    k1, b = 1.2, 0.75

    def _tf(self, word: str, doc: list[str], mean_len: float) -> float:
        n = doc.count(word)
        norm = self.k1 * (1 - self.b + self.b * len(doc) / mean_len)
        return n * (self.k1 + 1) / (n + norm)


class LeadBiasedSelector(_Lexical):
    """Order-sensitive: a word counts by its earliest position, halving every 10 tokens."""

    half_life = 10

    def _tf(self, word: str, doc: list[str], mean_len: float) -> float:
        return 0.5 ** (doc.index(word) / self.half_life) if word in doc else 0.0


class CommandSelector:
    """Bridge to a real model: JSON on stdin, chosen tool name on stdout.

    A crash or timeout raises, because an infrastructure fault is not a wrong answer.
    """

    def __init__(self, argv: Sequence[str], timeout: float = 60.0) -> None:
        self.argv = list(argv)
        self.timeout = timeout

    def select(self, query: str, tools: Sequence[Tool]) -> str | None:
        payload = json.dumps({"query": query, "tools": [t._asdict() for t in tools]})
        done = subprocess.run(
            self.argv,
            input=payload,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=True,
        )
        return done.stdout.strip() or None
