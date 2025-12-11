"""
Shared constants for the BioPortal tagging utility.
"""

from pathlib import Path

BASE_URL = "https://data.bioontology.org"
ENV_API_KEY = "BIOPORTAL_API_KEY"
DEFAULT_DOWNLOADS_DIR = Path("downloads")

__all__ = ["BASE_URL", "ENV_API_KEY", "DEFAULT_DOWNLOADS_DIR"]

