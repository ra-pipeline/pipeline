#!/usr/bin/env python3
"""Fetch and update the Pipeline BibTeX references from the NASA SciX (formerly ADS) public library.

Library URL: https://scixplorer.org/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg
(Legacy URL: https://ui.adsabs.harvard.edu/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg)

Usage:
    # Set your SciX / ADS API token:
    export SCIX_API_TOKEN="your-token"   # or ADS_DEV_KEY="your-token"
    pixi run update-references

    # Or run directly:
    python scripts/update_references.py [--token <TOKEN>] [--output <PATH>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_LIBRARY_ID = "w9Eg1EwtTAK14nz2CuQ2Fg"
DEFAULT_OUTPUT_REL = Path("docs/source/references/pipeline.bib")
DEFAULT_API_BASE = os.environ.get("SCIX_API_BASE", "https://api.scixplorer.org/v1")
FALLBACK_API_BASE = "https://api.adsabs.harvard.edu/v1"


def get_api_token(arg_token: str | None = None) -> str | None:
    """Retrieve the SciX / ADS API token from arguments, environment variables, or config files."""
    if arg_token:
        return arg_token.strip()

    # 1. Check environment variables (SciX preferred, then legacy ADS)
    env_vars = [
        "SCIX_API_TOKEN",
        "SCIX_DEV_KEY",
        "ADS_DEV_KEY",
        "ADS_API_TOKEN",
        "ADSTOKEN",
    ]
    for var in env_vars:
        token = os.environ.get(var)
        if token and token.strip():
            return token.strip()

    # 2. Check standard SciX and ADS token files
    token_files = [
        Path.home() / ".scix" / "token",
        Path.home() / ".scix" / "dev_key",
        Path.home() / ".config" / "scix" / "token",
        Path.home() / ".config" / "scix" / "dev_key",
        Path.home() / ".ads" / "dev_key",
        Path.home() / ".ads" / "token",
        Path.home() / ".config" / "ads" / "dev_key",
        Path.home() / ".config" / "ads" / "token",
    ]
    for path in token_files:
        if path.is_file():
            try:
                t = path.read_text(encoding="utf-8").strip()
                if t:
                    return t
            except Exception:
                pass

    return None


# Backwards compatibility alias
get_ads_token = get_api_token


def fetch_library_bibcodes(
    library_id: str,
    token: str,
    api_base: str = DEFAULT_API_BASE,
) -> list[str]:
    """Fetch all bibcodes contained in the specified public library."""
    base_url = f"{api_base.rstrip('/')}/biblib/libraries/{library_id}"
    params = urllib.parse.urlencode({"rows": 2000, "start": 0})
    url = f"{base_url}?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "ALMA-Pipeline-Doc-Update/1.0 (NASA SciX)",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print("Error: Unauthorized (401). Please check that your SciX/ADS API token is valid.", file=sys.stderr)
        elif exc.code == 404:
            print(f"Error: Library ID '{library_id}' not found (404).", file=sys.stderr)
        else:
            print(f"Error fetching library documents from {api_base}: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        if api_base == DEFAULT_API_BASE and DEFAULT_API_BASE != FALLBACK_API_BASE:
            print(
                f"Warning: Connection to {DEFAULT_API_BASE} failed ({exc.reason}). Retrying with {FALLBACK_API_BASE} ...",
                file=sys.stderr,
            )
            return fetch_library_bibcodes(library_id, token, api_base=FALLBACK_API_BASE)
        print(f"Error connecting to API ({api_base}): {exc.reason}", file=sys.stderr)
        sys.exit(1)

    documents = data.get("documents", [])
    return documents


def export_bibtex(
    bibcodes: list[str],
    token: str,
    api_base: str = DEFAULT_API_BASE,
) -> str:
    """Export a list of bibcodes to a formatted BibTeX string using the Export API."""
    if not bibcodes:
        return ""

    url = f"{api_base.rstrip('/')}/export/bibtexabs"
    payload = {
        "bibcode": bibcodes,
        "sort": "year desc, bibcode desc",
        "style": "default",
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ALMA-Pipeline-Doc-Update/1.0 (NASA SciX)",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"Error exporting BibTeX from {api_base}: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        if api_base == DEFAULT_API_BASE and DEFAULT_API_BASE != FALLBACK_API_BASE:
            print(
                f"Warning: Connection to {DEFAULT_API_BASE} failed ({exc.reason}). Retrying with {FALLBACK_API_BASE} ...",
                file=sys.stderr,
            )
            return export_bibtex(bibcodes, token, api_base=FALLBACK_API_BASE)
        print(f"Error connecting to API ({api_base}): {exc.reason}", file=sys.stderr)
        sys.exit(1)

    return data.get("export", "")


def extract_entry_keys(bibtex_content: str) -> set[str]:
    """Extract entry keys (e.g. 2023PASP..135g4501H) from BibTeX content."""
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bibtex_content))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch latest BibTeX references from NASA SciX (formerly ADS) public library."
    )
    parser.add_argument(
        "--token",
        "-t",
        help="NASA SciX/ADS API Token (defaults to $SCIX_API_TOKEN, $ADS_DEV_KEY, or ~/.scix/token, ~/.ads/dev_key)",
    )
    parser.add_argument(
        "--library-id",
        "-l",
        default=DEFAULT_LIBRARY_ID,
        help=f"Library ID (default: {DEFAULT_LIBRARY_ID})",
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"API Base URL (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help=f"Output .bib file path (default: {DEFAULT_OUTPUT_REL})",
    )

    args = parser.parse_args()

    token = get_api_token(args.token)
    if not token:
        print(
            "Error: NASA SciX / ADS API Token is required.\n\n"
            "Please provide a token via one of the following:\n"
            "  1. Private config file (Recommended):\n"
            "     mkdir -p ~/.scix && echo \"<your_token>\" > ~/.scix/token && chmod 600 ~/.scix/token\n"
            "     (or ~/.ads/dev_key for legacy ADS setups)\n"
            "  2. Environment variable: export SCIX_API_TOKEN=\"<your_token>\"\n"
            "     (or export ADS_DEV_KEY=\"<your_token>\")\n"
            "  3. Command line: python scripts/update_references.py --token <your_token>\n\n"
            "To get a free API Token:\n"
            "  - Log in to NASA SciX: https://scixplorer.org/\n"
            "  - Go to Settings -> API Token: https://scixplorer.org/user/settings/token\n"
            "  (or NASA/ADS: https://ui.adsabs.harvard.edu/user/settings/token)",
            file=sys.stderr,
        )
        sys.exit(1)

    # Determine project root directory
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    if args.output:
        output_path = args.output.resolve()
    else:
        output_path = project_root / DEFAULT_OUTPUT_REL

    print(f"Fetching library documents for library ID: {args.library_id} via {args.api_base} ...")
    bibcodes = fetch_library_bibcodes(args.library_id, token, api_base=args.api_base)
    print(f"Found {len(bibcodes)} papers in library.")

    if not bibcodes:
        print("Warning: No documents found in library. Aborting update.", file=sys.stderr)
        sys.exit(1)

    print(f"Exporting BibTeX from {args.api_base} ...")
    bibtex_content = export_bibtex(bibcodes, token, api_base=args.api_base)

    if not bibtex_content.strip():
        print("Error: Empty BibTeX received from API.", file=sys.stderr)
        sys.exit(1)

    # Compare with existing file
    old_keys = set()
    if output_path.exists():
        try:
            old_keys = extract_entry_keys(output_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    new_keys = extract_entry_keys(bibtex_content)
    added = new_keys - old_keys
    removed = old_keys - new_keys

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(bibtex_content, encoding="utf-8")
    print(f"Successfully updated {output_path} ({len(new_keys)} entries).")

    if added:
        print(f"  + Added {len(added)} new entries: {', '.join(sorted(added))}")
    if removed:
        print(f"  - Removed {len(removed)} entries: {', '.join(sorted(removed))}")
    if not added and not removed:
        print("  (No entry changes; content refreshed)")


if __name__ == "__main__":
    main()
