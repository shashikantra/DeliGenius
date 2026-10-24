from __future__ import annotations

import re
from typing import Protocol

from deli_rag.config.settings import get_config


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class HeuristicTokenCounter:
    """Approximates token count as words + punctuation marks.

    Close enough for chunk-size enforcement. Will be swapped for the embedder's
    real tokenizer in Phase 2 by calling `set_token_counter()`. The heuristic
    over-counts slightly vs. BPE, which is the safe direction: chunks come out
    a bit smaller than the limit, never larger.
    """
    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(_TOKEN_RE.findall(text))


_counter: TokenCounter = HeuristicTokenCounter()


def set_token_counter(counter: TokenCounter) -> None:
    global _counter
    _counter = counter


def count_tokens(text: str) -> int:
    return _counter.count(text)


def within_limit(text: str, limit: int) -> bool:
    return count_tokens(text) <= limit


# Sanity check against config at import
_cfg = get_config()
assert _cfg.chunking.child_max_tokens >= _cfg.chunking.child_target_tokens, \
    "config invariant: child_max_tokens must be >= child_target_tokens"