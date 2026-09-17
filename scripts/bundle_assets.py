#!/usr/bin/env python3
"""Bundle and minify weblog static JavaScript and CSS assets.

This script replaces the legacy setup.py MinifyJSCommand and MinifyCSSCommand,
allowing minified weblog assets to be generated independently of the package build process.

Usage:
    python scripts/bundle_assets.py          # Generate and write minified assets
    python scripts/bundle_assets.py --check  # Verify minified assets are up-to-date
"""

import argparse
import logging
import sys
from pathlib import Path

try:
    import csscompressor
    from jsmin import jsmin
except ImportError as e:
    sys.exit(
        f"Error: Missing required dependency for asset bundling: {e}\n"
        "Please install 'csscompressor' and 'jsmin' (e.g. via 'pip install .[dev]' or 'python scripts/install_dependencies.py --dev')."
    )

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ENCODING = "utf-8"

# Source files mapping to target bundle
JS_BUNDLES = {
    "pipeline_common.min.js": [
        "jquery-3.3.1.js",
        "holder.js",
        "lazyload.js",
        "jquery.fancybox.js",
        "plotcmd.js",
        "tcleancmd.js",
        "purl.js",
        "bootstrap.js",
        "pipeline.js",
    ],
    "pipeline_plots.min.js": [
        "select2.js",
        "d3.v3.js",
    ],
}

CSS_BUNDLES = {
    "all.min.css": [
        "font-awesome.css",
        "jquery.fancybox.css",
        "select2.css",
        "select2-bootstrap.css",
        "pipeline.css",
    ],
}


def minify_js(input_paths: list[Path]) -> str:
    """Minify and bundle a list of JavaScript files using jsmin."""
    minified_chunks = []
    for path in input_paths:
        with open(path, "r", encoding=ENCODING) as f:
            content = f.read()
        minified_chunks.append(f"// from {path.name}")
        minified_chunks.append(jsmin(content, quote_chars="'\"`"))
    return "\n".join(minified_chunks) + "\n"


def minify_css(input_paths: list[Path]) -> str:
    """Minify and bundle a list of CSS files using csscompressor."""
    buffer = []
    for path in input_paths:
        with open(path, "r", encoding=ENCODING) as f:
            buffer.append(f.read())
    combined = "\n\n".join(buffer)
    compressed = csscompressor.compress(combined)
    return compressed + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that minified bundles on disk are up to date without modifying them (exits 1 if out of sync).",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress informational output.",
    )
    args = parser.parse_args()

    if args.quiet:
        logger.setLevel(logging.WARNING)

    # Locate package resources directory relative to script
    repo_root = Path(__file__).resolve().parent.parent
    resources_dir = repo_root / "pipeline" / "infrastructure" / "renderer" / "templates" / "resources"
    js_dir = resources_dir / "js"
    css_dir = resources_dir / "css"

    if not js_dir.is_dir() or not css_dir.is_dir():
        logger.error("Could not find weblog template resources directories at: %s", resources_dir)
        return 1

    out_of_sync = False

    # Process JavaScript bundles
    for bundle_name, input_files in JS_BUNDLES.items():
        output_file = js_dir / bundle_name
        input_paths = [js_dir / f for f in input_files]
        for path in input_paths:
            if not path.is_file():
                logger.error("Missing input file: %s", path)
                return 1

        logger.info("Minifying JavaScript bundle: %s", bundle_name)
        new_content = minify_js(input_paths)

        if args.check:
            if not output_file.is_file():
                logger.error("Bundle missing: %s", output_file)
                out_of_sync = True
            else:
                existing_content = output_file.read_text(encoding=ENCODING)
                if existing_content != new_content:
                    logger.error("Bundle out of sync: %s", output_file)
                    out_of_sync = True
        else:
            output_file.write_text(new_content, encoding=ENCODING)
            logger.info("Wrote %s (%d bytes)", output_file, len(new_content))

    # Process CSS bundles
    for bundle_name, input_files in CSS_BUNDLES.items():
        output_file = css_dir / bundle_name
        input_paths = [css_dir / f for f in input_files]
        for path in input_paths:
            if not path.is_file():
                logger.error("Missing input file: %s", path)
                return 1

        logger.info("Minifying CSS bundle: %s", bundle_name)
        new_content = minify_css(input_paths)

        if args.check:
            if not output_file.is_file():
                logger.error("Bundle missing: %s", output_file)
                out_of_sync = True
            else:
                existing_content = output_file.read_text(encoding=ENCODING)
                if existing_content != new_content:
                    logger.error("Bundle out of sync: %s", output_file)
                    out_of_sync = True
        else:
            output_file.write_text(new_content, encoding=ENCODING)
            logger.info("Wrote %s (%d bytes)", output_file, len(new_content))

    if args.check and out_of_sync:
        logger.error("One or more minified bundles are missing or out of sync with source assets.")
        return 1

    if args.check:
        logger.info("All minified bundles are up to date.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

