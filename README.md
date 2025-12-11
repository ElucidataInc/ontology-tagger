## Ontology Tagger Utility

This repo provides a modular Python utility to:
- Fetch a specific BioPortal ontology version (OWL) by submission ID/version.
- Annotate terms via the BioPortal Annotator API.
- Verify whether annotated concepts exist in the specified ontology version, with strict or flexible fallback to the latest.

### Prerequisites
- Python 3.9+ recommended.
- BioPortal account and API key (free signup).
- `pip install -r requirements.txt`

### Obtain your BioPortal API key
1) Visit https://bioportal.bioontology.org/accounts/new and sign up / log in.
2) Go to your account page → API Key → copy the key.

### Configure the API key
Set the key in your environment (preferred) or a `.env` file:
```bash
export BIOPORTAL_API_KEY=your_key_here
# or create .env in the repo root:
echo "BIOPORTAL_API_KEY=your_key_here" > .env
```

### Install dependencies
```bash
pip install -r requirements.txt
```

### CLI usage
```bash
python main.py \
  --ontology CL \
  --terms melanocyte keratinocyte \
  # or use a text file with one term per line:
  # --file terms.txt \
  --version 2025-10-16 \
  --downloads-dir downloads
```

### Python / Notebook usage
```python
from pathlib import Path
from tagger import BioPortalClient, OntologyTagger
from utils import get_api_key, outcomes_to_json, save_json_output

client = BioPortalClient(api_key=get_api_key())
tagger = OntologyTagger(client)

# Strict: raise if version missing; if concept absent in version, mark strict mismatch.
outcomes = tagger.annotate_terms(
    ontology="CL",
    terms=["melanocyte"],
    version="2025-10-16",
    on_version_missing="error",
)
print(outcomes_to_json(outcomes))

# Flexible: if version missing or concept absent there, fall back to latest.
outcomes = tagger.annotate_terms(
    ontology="CL",
    terms=["melanocyte"],
    version="2025-10-16",
    on_version_missing="latest",
)
print(outcomes_to_json(outcomes))

# File input: one term per line in terms.txt
outcomes = tagger.annotate_terms(
    ontology="CL",
    file_path=Path("terms.txt"),
    version="2025-10-16",
    on_version_missing="latest",
)
print(outcomes_to_json(outcomes))

# Save results to a JSON file
outcomes = tagger.annotate_terms(
    ontology="CL",
    terms=["melanocyte", "keratinocyte"],
    version="2025-10-16",
)
save_json_output(outcomes, Path("results.json"))
```

### Behavior summary
- `on_version_missing="error"`: strict; requires the specified version and the concept to exist in that version. Otherwise returns a strict mismatch (no fallback).
- `on_version_missing="latest"`: flexible; if version is missing or the concept isn’t in that version, it annotates with the latest and notes the fallback in the comment.
- Downloads are cached in `downloads/{ontology}_{version}.owl`; subsequent runs reuse the file.
- Annotated ontology IDs are stored as short fragments (no full URIs).

### Files of interest
- `tagger.py`: BioPortal client, download, annotation orchestration, version checks.
- `utils.py`: env/key loading, normalization, JSON helpers (including `save_json_output` for saving results to files).
- `const.py`: base URL, env var name, default download dir.
- `main.py`: CLI entry point.

### Troubleshooting
- If you change code, restart your notebook kernel to pick up new class definitions.
- If an OWL download is actually JSON (metadata), ensure the `submissionId` exists and the URL includes `/download` with your `apikey`.
- Verify `client.last_download_url` after a run to see the exact download endpoint used.

