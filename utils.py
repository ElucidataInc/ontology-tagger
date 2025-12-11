"""
Utility helpers for BioPortal tagging.
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.request
from typing import Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

from const import ENV_API_KEY


def load_env_once() -> None:
    # Safe to call repeatedly; load_dotenv is idempotent.
    load_dotenv()


def get_api_key(env_var: str = ENV_API_KEY, default: Optional[str] = None) -> str:
    load_env_once()
    key = os.getenv(env_var, default)
    if not key:
        raise RuntimeError(
            f"Set the BioPortal API key in environment variable '{env_var}' "
            "or in a .env file."
        )
    return key


def build_opener(api_key: str) -> urllib.request.OpenerDirector:
    opener = urllib.request.build_opener()
    opener.addheaders = [("Authorization", f"apikey token={api_key}")]
    return opener


def json_get(opener: urllib.request.OpenerDirector, url: str):
    with opener.open(url) as resp:
        return json.loads(resp.read())


def normalize_terms(
    terms: Optional[Iterable[str]] = None, file_path: Optional[pathlib.Path] = None
) -> List[str]:
    if terms is None and file_path is None:
        raise ValueError("Provide either `terms` or `file_path`.")

    collected: List[str] = []

    if terms is not None:
        for term in terms:
            if term is None:
                continue
            for line in str(term).splitlines():
                cleaned = line.strip()
                if cleaned:
                    collected.append(cleaned)

    if file_path:
        for raw in pathlib.Path(file_path).read_text().splitlines():
            cleaned = raw.strip()
            if cleaned:
                collected.append(cleaned)

    return collected


def outcomes_to_json(outcomes: Sequence[object]) -> str:
    serialized: List[Dict[str, Optional[str]]] = []
    for outcome in outcomes:
        if hasattr(outcome, "to_dict"):
            serialized.append(outcome.to_dict())
        elif isinstance(outcome, dict):
            serialized.append(outcome)  # type: ignore[arg-type]
        else:
            raise TypeError(
                "outcomes_to_json expects items with to_dict() or dictionaries."
            )
    return json.dumps(serialized, indent=2)


__all__ = [
    "build_opener",
    "get_api_key",
    "json_get",
    "load_env_once",
    "normalize_terms",
    "outcomes_to_json",
]

