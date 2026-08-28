#!/usr/bin/env python3
"""
Fetch and update the Pipeline BibTeX references from the NASA/ADS public library.

Library URL: https://ui.adsabs.harvard.edu/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg

Usage:
    # Set your ADS API token:
    export ADS_DEV_KEY="your-ads-token"  # or ADS_API_TOKEN="your-ads-token"
    pixi run update-references

    # Or run directly:
    python scripts/update_references.py [--token <TOKEN>] [--output <PATH>]
"""

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


def get_ads_token(arg_token: str | None = None) -> str | None:
    """Retrieve the ADS API token from arguments, environment variables, or config files."""
    if arg_token:
        return arg_token.strip()

    # 1. Check environment variables
    token = (
        os.environ.get("ADS_DEV_KEY")
        or os.environ.get("ADS_API_TOKEN")
        or os.environ.get("ADSTOKEN")
    )
    if token and token.strip():
        return token.strip()

    # 2. Check standard NASA/ADS token files (~/.ads/dev_key, ~/.ads/token, ~/.config/ads/dev_key)
    token_files = [
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


def fetch_library_bibcodes(library_id: str, token: str) -> list[str]:
    """Fetch all bibcodes contained in the specified ADS public library."""
    base_url = f"https://api.adsabs.harvard.edu/v1/biblib/libraries/{library_id}"
    params = urllib.parse.urlencode({"rows": 2000, "start": 0})
    url = f"{base_url}?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "ALMA-Pipeline-Doc-Update/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print("Error: Unauthorized (401). Please check that your ADS API token is valid.", file=sys.stderr)
        elif exc.code == 404:
            print(f"Error: Library ID '{library_id}' not found (404).", file=sys.stderr)
        else:
            print(f"Error fetching library documents from ADS: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Error connecting to ADS API: {exc.reason}", file=sys.stderr)
        sys.exit(1)

    documents = data.get("documents", [])
    return documents


def export_bibtex(bibcodes: list[str], token: str) -> str:
    """Export a list of bibcodes to a formatted BibTeX string using the ADS Export API."""
    if not bibcodes:
        return ""

    url = "https://api.adsabs.harvard.edu/v1/export/bibtexabs"
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
            "User-Agent": "ALMA-Pipeline-Doc-Update/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"Error exporting BibTeX from ADS API: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Error connecting to ADS API: {exc.reason}", file=sys.stderr)
        sys.exit(1)

    return data.get("export", "")


def extract_entry_keys(bibtex_content: str) -> set[str]:
    """Extract entry keys (e.g. 2023PASP..135g4501H) from BibTeX content."""
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bibtex_content))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch latest BibTeX references from NASA/ADS public library."
    )
    parser.add_argument(
        "--token",
        "-t",
        help="NASA/ADS API Token (defaults to $ADS_DEV_KEY or $ADS_API_TOKEN)",
    )
    parser.add_argument(
        "--library-id",
        "-l",
        default=DEFAULT_LIBRARY_ID,
        help=f"NASA/ADS library ID (default: {DEFAULT_LIBRARY_ID})",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help=f"Output .bib file path (default: {DEFAULT_OUTPUT_REL})",
    )

    args = parser.parse_args()

    token = get_ads_token(args.token)
    if not token:
        print(
            "Error: NASA/ADS API Token is required.\n\n"
            "Please provide a token via one of the following:\n"
            "  1. Private config file (Recommended):\n"
            "     mkdir -p ~/.ads && echo \"<your_token>\" > ~/.ads/dev_key && chmod 600 ~/.ads/dev_key\n"
            "  2. Environment variable: export ADS_DEV_KEY=\"<your_token>\"\n"
            "     (or export ADS_API_TOKEN=\"<your_token>\")\n"
            "  3. Command line: python scripts/update_references.py --token <your_token>\n\n"
            "To get a free NASA/ADS API Token:\n"
            "  - Log in to NASA/ADS: https://ui.adsabs.harvard.edu/\n"
            "  - Go to Settings -> API Token: https://ui.adsabs.harvard.edu/user/settings/token\n"
            "  - Generate a new token.",
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

    print(f"Fetching library documents for library ID: {args.library_id} ...")
    bibcodes = fetch_library_bibcodes(args.library_id, token)
    print(f"Found {len(bibcodes)} papers in library.")

    if not bibcodes:
        print("Warning: No documents found in library. Aborting update.", file=sys.stderr)
        sys.exit(1)

    print("Exporting BibTeX from ADS...")
    bibtex_content = export_bibtex(bibcodes, token)

    if not bibtex_content.strip():
        print("Error: Empty BibTeX received from ADS.", file=sys.stderr)
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
