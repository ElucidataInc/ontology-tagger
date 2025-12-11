"""
Simple CLI entrypoint for BioPortal ontology tagging.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from const import DEFAULT_DOWNLOADS_DIR
from tagger import BioPortalClient, OntologyTagger
from utils import get_api_key, outcomes_to_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tag terms using BioPortal.")
    parser.add_argument(
        "--ontology",
        required=True,
        help="Ontology acronym to use (e.g., CL).",
    )
    parser.add_argument(
        "--version",
        help="Optional ontology version to verify against. Defaults to latest.",
    )
    parser.add_argument(
        "--terms",
        nargs="+",
        help="List of terms to annotate.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Text file with one term per line to annotate.",
    )
    parser.add_argument(
        "--downloads-dir",
        type=Path,
        default=DEFAULT_DOWNLOADS_DIR,
        help=f"Where to cache OWL downloads (default: {DEFAULT_DOWNLOADS_DIR}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.terms and not args.file:
        raise SystemExit("Provide --terms or --file with terms to annotate.")

    api_key = get_api_key()
    client = BioPortalClient(api_key=api_key)
    tagger = OntologyTagger(client, downloads_dir=args.downloads_dir)

    outcomes = tagger.annotate_terms(
        ontology=args.ontology,
        terms=args.terms,
        file_path=args.file,
        version=args.version,
    )
    print(outcomes_to_json(outcomes))


if __name__ == "__main__":
    main()

