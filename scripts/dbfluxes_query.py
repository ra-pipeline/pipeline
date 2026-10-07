r"""dbfluxes_query.py - Query the flux density catalogue service for a single source.

This wraps `dbfluxes.fluxservice` so one (source, date, frequency) lookup can be run outside of a pipeline
session, e.g. to check what the catalogue returns for a calibrator.

Usage:

    pixi run python scripts/dbfluxes_query.py --name <source> --date <date> --frequency <Hz> [--url URL] [--json]

Arguments:
    --date       ISO 8601 date or datetime. A value without a timezone is interpreted as UTC. Only the calendar day
                 (UTC) is sent to the service; any time of day is accepted but ignored.
    --frequency  Frequency in Hz. Exponent notation is accepted and expanded to a plain decimal string before the
                 query is built. Zero, negative, NaN and infinite values are rejected.
    --url        Flux service URL. Defaults to the primary URL from `dbfluxes.get_flux_urls()`, so a
                 FLUX_SERVICE_URL override is honoured.
    --json       Print the result as JSON instead of aligned key/value lines.

Examples:

    # Date only, frequency in exponent notation.
    pixi run python scripts/dbfluxes_query.py --name J1427-4206 --date 2013-03-27 --frequency 86.837309056e9

    # Datetime (time part ignored), plain frequency, JSON output.
    pixi run python scripts/dbfluxes_query.py --name J1427-4206 --date 2013-03-27T07:53:03 \
        --frequency 86837309056.169219970703125 --json

    # Query a specific service instance.
    pixi run python scripts/dbfluxes_query.py --name J1427-4206 --date 2013-03-27 --frequency 86.837309056e9 \
        --url https://example.org/sc/flux

Output:
    The result goes to stdout. Pipeline log messages go to stderr, so `--json` output can be piped to other tools.

Exit codes:
    0: the service returned a row with a usable flux density.
    1: the service could not be reached or its response could not be parsed.
    2: the service responded but returned no row, or a row without a usable flux density (the row is still printed
       if there is one, since it may carry a clarification message).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import decimal
import json
import sys
from collections.abc import Sequence
from xml.parsers.expat import ExpatError

# The pipeline's loggers write to sys.stdout, bound when pipeline.infrastructure.logging is first imported. Import
# under a stdout->stderr redirect so log output stays off stdout and the result (e.g. --json) can be piped.
with contextlib.redirect_stdout(sys.stderr):
    from pipeline.hifa.tasks.importdata import dbfluxes

EXIT_OK = 0
EXIT_QUERY_FAILED = 1
EXIT_NO_DATA = 2


def _parse_date(value: str) -> datetime.datetime:
    """Parse an ISO 8601 date or datetime string into a timezone-aware UTC datetime."""
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f'invalid date {value!r}; use ISO 8601, e.g. 2013-03-27 or 2013-03-27T07:53:03'
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _parse_frequency(value: str) -> str:
    """Validate a frequency in Hz and return it as a plain decimal string (no exponent)."""
    try:
        freq = decimal.Decimal(value)
    except decimal.InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f'invalid frequency {value!r}; expected a number in Hz') from exc
    if not freq.is_finite() or freq <= 0:
        raise argparse.ArgumentTypeError(f'invalid frequency {value!r}; must be a positive number in Hz')
    return format(freq, 'f')


def _has_usable_flux(result: dict[str, str | None]) -> bool:
    """Return True if the row holds a positive flux density and a real spectral index.

    This is the same validity test `dbfluxes.query_online_catalogue` applies (flux density > 0 and spectral index
    not equal to the -1000 "unknown" sentinel).
    """
    try:
        flux = float(result['fluxdensity'])
        spix = float(result['spectralindex'])
    except (KeyError, TypeError, ValueError):
        return False
    return flux > 0.0 and spix != -1000


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog='dbfluxes_query.py',
        description='Query the flux density catalogue service for one source, date and frequency.',
    )
    parser.add_argument('--name', required=True, help='source name, e.g. J1427-4206')
    parser.add_argument('--date', required=True, type=_parse_date, help='observation date or datetime (ISO 8601, UTC)')
    parser.add_argument('--frequency', required=True, type=_parse_frequency, help='frequency in Hz')
    parser.add_argument(
        '--url',
        default=None,
        help='flux service URL; defaults to the primary URL used by the pipeline (FLUX_SERVICE_URL override honoured)',
    )
    parser.add_argument('--json', action='store_true', dest='as_json', help='print the result as JSON')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the query and print the result.

    Args:
        argv: Command line arguments excluding the program name. Defaults to `sys.argv[1:]`.

    Returns:
        Process exit code, see the module docstring.
    """
    args = build_parser().parse_args(argv)
    service_url = args.url if args.url is not None else dbfluxes.get_flux_urls()[0]

    try:
        result = dbfluxes.fluxservice(service_url, args.date, args.frequency, args.name)
    except (OSError, ExpatError) as exc:
        print(
            f'Query to {service_url} failed: {exc}\nCheck network access and the --url value, or retry later.',
            file=sys.stderr,
        )
        return EXIT_QUERY_FAILED

    if not result:
        print(
            f'No catalogue row returned for {args.name} at {args.frequency} Hz on {args.date:%Y-%m-%d}.',
            file=sys.stderr,
        )
        return EXIT_NO_DATA

    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        width = max(len(key) for key in result)
        for key, value in result.items():
            print(f'{key:<{width}}  {value}')

    if not _has_usable_flux(result):
        print(
            f'Catalogue row for {args.name} has no usable flux density '
            f'(status code {result.get("statuscode")}, clarification: {result.get("clarification")}).',
            file=sys.stderr,
        )
        return EXIT_NO_DATA
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
