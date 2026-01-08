"""
Core tagging logic: BioPortal client, OWL inspection, and orchestration.
"""

from __future__ import annotations

import pathlib
import logging
import urllib.parse
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from const import BASE_URL, DEFAULT_DOWNLOADS_DIR
from utils import build_opener, json_get, normalize_terms


class OntologyVersionNotFound(ValueError):
    """Raised when a requested ontology version is unavailable."""

    def __init__(self, ontology: str, version: str, available: Sequence[str]):
        msg = (
            f"Version '{version}' not found for ontology '{ontology}'. "
            f"Available versions: {', '.join(available) or 'none'}"
        )
        super().__init__(msg)
        self.ontology = ontology
        self.version = version
        self.available = list(available)


class BioPortalClient:
    """
    Minimal wrapper around the BioPortal REST API.
    """

    def __init__(self, api_key: str, base_url: str = BASE_URL):
        if not api_key:
            raise ValueError("api_key is required for BioPortal access.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._opener = build_opener(api_key)
        self.last_download_url: Optional[str] = None

    def _url(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        path = path.lstrip("/")
        url = f"{self.base_url}/{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def list_ontologies(self):
        resources = json_get(self._opener, self._url("/"))
        return json_get(self._opener, resources["links"]["ontologies"])

    def list_submissions(self, ontology: str):
        """
        Returns all submissions (versions) for an ontology acronym.
        """
        return json_get(self._opener, self._url(f"/ontologies/{ontology}/submissions"))

    def annotate_text(
        self, text: str, ontology: str, extra_params: Optional[Dict[str, str]] = None
    ):
        params = {"text": text, "ontologies": ontology}
        if extra_params:
            params.update(extra_params)
        return json_get(self._opener, self._url("/annotator", params))

    def download_submission(
        self, ontology: str, version: Optional[str], dest_dir: pathlib.Path
    ) -> Tuple[pathlib.Path, str]:
        """
        Download a specific ontology submission (OWL) to dest_dir.

        Returns (path, resolved_version).
        """
        submissions = self.list_submissions(ontology)
        if not submissions:
            raise OntologyVersionNotFound(ontology, version or "latest", [])

        if version:
            matches = [
                sub for sub in submissions if str(sub.get("version") or "") == version
            ]
            if not matches:
                available = [str(sub.get("version") or "") for sub in submissions]
                raise OntologyVersionNotFound(ontology, version, available)
            submission = matches[0]
        else:
            submission = submissions[0]

        resolved_version = str(submission.get("version") or "latest")
        submission_id = submission.get("submissionId")
        if not submission_id:
            raise RuntimeError("No submissionId found in submission payload.")

        # Always construct download URL from submissionId to ensure we get the binary OWL file
        download_url = (
            f"{self.base_url}/ontologies/{ontology}/submissions/"
            f"{submission_id}/download"
        )

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{ontology}_{resolved_version}.owl"

        # Reuse existing download if present.
        if dest_path.exists():
            self.last_download_url = f"(cached) {dest_path}"
            return dest_path, resolved_version

        separator = "&" if "?" in download_url else "?"
        final_url = download_url + f"{separator}apikey={self.api_key}"
        self.last_download_url = final_url

        # Download raw content with requests; include Authorization header.
        import requests  # type: ignore[import-unresolved]

        resp = requests.get(
            final_url,
            headers={
                "Accept": "application/rdf+xml, application/xml;q=0.9, */*;q=0.1",
                "Authorization": f"apikey token={self.api_key}",
            },
            timeout=30,
        )
        resp.raise_for_status()
        
        # Verify we got OWL/RDF content, not JSON metadata
        content_type = resp.headers.get("Content-Type", "").lower()
        if "json" in content_type or (len(resp.content) > 0 and resp.content[:1] == b"{"):
            raise ValueError(
                f"Downloaded JSON metadata instead of OWL file. "
                f"URL: {final_url}\n"
                f"Content-Type: {resp.headers.get('Content-Type')}\n"
                f"Submission ID used: {submission_id}\n"
                f"Version: {resolved_version}\n"
                f"First 200 bytes: {resp.content[:200].decode(errors='replace')}"
            )
        
        dest_path.write_bytes(resp.content)

        return dest_path, resolved_version


class OwlLexicon:
    """
    Simple label index built from an OWL file to verify term presence.
    """

    def __init__(self, owl_path: pathlib.Path):
        try:
            import rdflib  # type: ignore[import-unresolved]
            from rdflib import (  # type: ignore[import-unresolved]
                RDF,
                RDFS,
                OWL,
            )  # noqa: F401
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError(
                "rdflib is required to inspect OWL content. "
                "Install via `pip install rdflib`."
            ) from exc

        self._labels = set()
        self._ids = set()
        self._id_to_label = {}
        graph = rdflib.Graph()
        try:
            graph.parse(str(owl_path))
        except Exception as exc:
            # Produce a clearer error if the downloaded file is not valid OWL/XML.
            raise ValueError(
                f"Failed to parse OWL file at '{owl_path}'. "
                "The downloaded content may not be a valid ontology; "
                "verify the version exists and the download link is correct."
            ) from exc

        # First pass: Collect all labels for subjects
        # We want to map ID -> Label.
        # IDs are derived from the Subject URI.
        for subj, _, obj in graph.triples((None, rdflib.RDFS.label, None)):
            label = str(obj).strip()
            if not label:
                continue
            
            # Add to labels set for forward check
            self._labels.add(label.lower())
            
            # Map ID to Label
            if isinstance(subj, rdflib.term.URIRef):
                ident = str(subj)
                # Logic to extract short_id must match what we do in OntologyTagger
                short_id = ident.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                # Store the original case label for the ID
                # If multiple labels exist, this simple approach takes the last one visited.
                # Ideally we might want 'prefLabel' but typical OWL uses rdfs:label.
                self._id_to_label[short_id.lower()] = label

        for subj, _, _ in graph.triples((None, None, None)):
            if isinstance(subj, rdflib.term.URIRef):
                ident = str(subj)
                short_id = ident.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                self._ids.add(short_id.lower())

    def has_label(self, label: str) -> bool:
        return label.lower().strip() in self._labels

    def has_id(self, ident: str) -> bool:
        return ident.lower().strip() in self._ids
    
    def get_label_by_id(self, ident: str) -> Optional[str]:
        """
        Reverse lookup: Get the label for a given ontology ID (case-insensitive on ID).
        """
        return self._id_to_label.get(ident.lower().strip())


@dataclass
class AnnotationOutcome:
    input_text: str
    standardized_term: Optional[str]
    ontology_id: Optional[str]
    ontology_version: Optional[str]
    comment: str

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "input_text": self.input_text,
            "standardized_term": self.standardized_term,
            "ontology_id": self.ontology_id,
            "ontology_version": self.ontology_version,
            "comment": self.comment,
        }


class OntologyTagger:
    """
    Orchestrates annotation against BioPortal and verifies presence in
    versioned OWL downloads.
    """

    def __init__(
        self,
        client: BioPortalClient,
        downloads_dir: pathlib.Path = DEFAULT_DOWNLOADS_DIR,
    ):
        self.client = client
        self.downloads_dir = downloads_dir

    def annotate_terms(
        self,
        ontology: str,
        terms: Optional[Iterable[str]] = None,
        file_path: Optional[pathlib.Path] = None,
        version: Optional[str] = None,
        on_version_missing: str = "error",
    ) -> List[AnnotationOutcome]:
        """
        Annotate terms and optionally verify against a specified ontology version.

        on_version_missing:
            - "error": strict — if the requested version is missing, raise; if the
              concept is absent in that version, report it as not matched there.
            - "latest": flexible — if the requested version is missing or the concept
              is absent in that version, fall back to latest.
        """
        prepared_terms = normalize_terms(terms, file_path)
        if not prepared_terms:
            return []

        submissions = self.client.list_submissions(ontology)
        latest_version = str(submissions[0].get("version") or "latest") if submissions else "latest"

        owl_path: Optional[pathlib.Path] = None
        resolved_version: Optional[str] = None
        owl_lexicon: Optional[OwlLexicon] = None
        version_fallback = False

        if version:
            matches = [sub for sub in submissions if str(sub.get("version") or "") == version]
            if not matches:
                if on_version_missing == "latest":
                    version_fallback = True
                    resolved_version = None
                    owl_lexicon = None
                else:
                    available = [str(sub.get("version") or "") for sub in submissions]
                    raise OntologyVersionNotFound(ontology, version, available)
            else:
                submission = matches[0]
                owl_path, resolved_version = self.client.download_submission(
                    ontology, version, self.downloads_dir
                )
                owl_lexicon = OwlLexicon(owl_path)
        else:
            # No version provided; operate on latest without lexicon verification.
            resolved_version = None

        outcomes: List[AnnotationOutcome] = []

        for term in prepared_terms:
            annotations = self.client.annotate_text(term, ontology)
            if not annotations:
                outcomes.append(
                    AnnotationOutcome(
                        input_text=term,
                        standardized_term=None,
                        ontology_id=None,
                        ontology_version=None,
                        comment="not matched at all",
                    )
                )
                continue

            top = annotations[0]
            class_details = top.get("annotatedClass", {})
            pref_label = class_details.get("prefLabel")
            ontology_uri = class_details.get("@id")
            short_id = None
            if ontology_uri:
                short_id = ontology_uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
            ontology_id = short_id

            # Reverse lookup and verification
            in_specified_version = False
            owl_label = None
            
            if owl_lexicon:
                if short_id:
                    in_specified_version = owl_lexicon.has_id(short_id)
                    # Attempt to get the label from the OWL file if we have the ID
                    if in_specified_version:
                        owl_label = owl_lexicon.get_label_by_id(short_id)
                
                if not in_specified_version and pref_label:
                    in_specified_version = owl_lexicon.has_label(pref_label)
                    # If we matched by label but not ID (rare if ID is missing), 
                    # we essentially trust pref_label is correct for that version 
                    # or implies the concept exists.

            # If we found a label in the OWL file, prioritize it as the standardized term
            # This fixes the issue where BioPortal might return null or we want the exact OWL string.
            final_standardized_term = owl_label if owl_label else pref_label

            if version and not version_fallback and in_specified_version:
                ont_version = resolved_version or version
                comment = "matched in user specified version"
            elif version and version_fallback:
                ont_version = latest_version
                comment = "requested version missing; matched in latest"
            elif version and not in_specified_version:
                if on_version_missing == "latest":
                    ont_version = latest_version
                    comment = "matched in latest, no match in specified version"
                else:
                    outcomes.append(
                        AnnotationOutcome(
                            input_text=term,
                            standardized_term=None,
                            ontology_id=ontology_id,
                            ontology_version=resolved_version or version,
                            comment="strict mode: not matched in specified version",
                        )
                    )
                    continue
            else:
                ont_version = latest_version
                comment = "matched in latest"

            outcomes.append(
                AnnotationOutcome(
                    input_text=term,
                    standardized_term=final_standardized_term,
                    ontology_id=ontology_id,
                    ontology_version=ont_version,
                    comment=comment,
                )
            )

        return outcomes


__all__ = [
    "AnnotationOutcome",
    "BioPortalClient",
    "OntologyTagger",
    "OntologyVersionNotFound",
]

