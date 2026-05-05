"""
Utility for selecting ASDM scans by VLA frequency band.

The function :func:`select_scans_by_vla_band` parses the raw ASDM XML tables
and returns a ``scans`` specification string directly usable as the ``scans``
argument to CASA ``importasdm``.

Usage example::

    from asdm_select_scans import select_scans_by_vla_band

    asdm = '/data/14A-339.sb29502161.eb29584626.56877.54292898148'
    scans_str = select_scans_by_vla_band(asdm, 'K')
    # e.g. returns '0:1~3,5,7~12'

    importasdm(asdm=asdm, vis='output.ms', scans=scans_str)
"""
import bisect
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Union


# Default VLA frequency band limits (Hz) and band designations.
# Mirrors the values in pipeline.infrastructure.tablereader.find_EVLA_band.
_VLA_BAND_LIMITS = [
    0.0e6, 150.0e6, 700.0e6, 2.0e9, 4.0e9, 8.0e9,
    12.0e9, 18.0e9, 26.5e9, 40.0e9, 56.0e9,
]
# One character per interval; '?' means undefined/out-of-range.
_VLA_BAND_LETTERS = '?4PLSCXUKAQ?'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_scans_by_vla_band(asdm_path: str, bands: Union[str, list], invert: bool = False) -> str:
    """Select ASDM scans whose spectral windows match the given VLA band(s).

    Parses the ASDM XML tables (SpectralWindow, DataDescription,
    ConfigDescription, Main, Scan) to identify which scans observe in the
    requested VLA frequency band(s).

    Args:
        asdm_path: Path to the root ASDM directory (the one containing
            ``SpectralWindow.xml``, ``Main.xml``, etc.).
        bands: One or more VLA band letter(s) to select.  May be a single
            string (e.g. ``'K'``) or a list (e.g. ``['L', 'S']``).
            Comparison is case-insensitive.  Valid band letters are:
            ``4`` (4-band, 0.15–0.7 GHz), ``P`` (0.7–2 GHz),
            ``L`` (1–2 GHz), ``S`` (2–4 GHz), ``C`` (4–8 GHz),
            ``X`` (8–12 GHz), ``U``/``Ku`` (12–18 GHz),
            ``K`` (18–26.5 GHz), ``A``/``Ka`` (26.5–40 GHz),
            ``Q`` (40–56 GHz).
        invert: When ``True``, return scans that do *not* contain any SPW in
            the requested band(s) — i.e. the complement of the normal
            selection.  Defaults to ``False``.

    Returns:
        A scan specification string in the ``importasdm`` ``scans`` format,
        e.g. ``'0:1~3,5,7~12'``.  Multiple exec blocks are separated by
        ``';'``.  Returns an empty string when no matching scans are found.

    Raises:
        FileNotFoundError: If a required ASDM XML table is not found under
            *asdm_path*.
        ValueError: If an unexpected XML structure is encountered.

    Example::

        scans_str = select_scans_by_vla_band('/data/my.asdm', ['K', 'Ka'])
        importasdm(asdm='/data/my.asdm', vis='output.ms', scans=scans_str)

        # Select every scan that is NOT K or Ka band
        scans_str = select_scans_by_vla_band('/data/my.asdm', ['K', 'Ka'], invert=True)
    """
    if isinstance(bands, str):
        bands = [bands]
    target_bands = {b.upper() for b in bands}

    # 1. SpectralWindow.xml  ->  spw_id (int): band letter (str)
    spw_band = _parse_spw_bands(os.path.join(asdm_path, 'SpectralWindow.xml'))

    # 2. DataDescription.xml  ->  dd_id (int): spw_id (int)
    dd_spw = _parse_dd_spw(os.path.join(asdm_path, 'DataDescription.xml'))

    # 3. ConfigDescription.xml  ->  cfg_id (int): set of dd_ids
    cfg_dds = _parse_cfg_dds(os.path.join(asdm_path, 'ConfigDescription.xml'))

    # 4. Main.xml  ->  (eb_id, scan_num): set of cfg_ids
    scan_cfgs = _parse_main_scan_cfgs(os.path.join(asdm_path, 'Main.xml'))

    # 5. Scan.xml  ->  list of (eb_id, scan_num) in ASDM order
    all_scans = _parse_scan_list(os.path.join(asdm_path, 'Scan.xml'))

    # 6. Filter: keep scans that contain at least one SPW in target bands
    eb_scans: dict = defaultdict(list)
    for eb_id, scan_num in all_scans:
        cfg_ids = scan_cfgs.get((eb_id, scan_num), set())
        scan_bands: set = set()
        for cfg_id in cfg_ids:
            for dd_id in cfg_dds.get(cfg_id, set()):
                spw_id = dd_spw.get(dd_id)
                if spw_id is not None:
                    scan_bands.add(spw_band.get(spw_id, 'unknown').upper())
        match = bool(scan_bands & target_bands)
        if match ^ invert:
            eb_scans[eb_id].append(scan_num)

    # 7. Format output: 'eb:scan_range[;eb:scan_range...]'
    parts = [
        f'{eb_id}:{_ints_to_range_str(scans)}'
        for eb_id, scans in sorted(eb_scans.items())
    ]
    return ';'.join(parts)


# ---------------------------------------------------------------------------
# ASDM XML parsers (private helpers)
# ---------------------------------------------------------------------------

def _parse_spw_bands(xml_path: str) -> dict:
    """Parse SpectralWindow.xml and return {spw_id: band_letter}."""
    _require_file(xml_path)
    spw_band = {}
    for row in ET.parse(xml_path).findall('row'):
        spw_id = _parse_asdm_id(row.findtext('spectralWindowId'))
        name = (row.findtext('name') or '').strip()
        band = _vla_band_from_spw_name(name)
        if band is None:
            ref_freq = float(row.findtext('refFreq') or 0)
            band = _freq_to_vla_band(ref_freq)
        spw_band[spw_id] = band
    return spw_band


def _parse_dd_spw(xml_path: str) -> dict:
    """Parse DataDescription.xml and return {dd_id: spw_id}."""
    _require_file(xml_path)
    dd_spw = {}
    for row in ET.parse(xml_path).findall('row'):
        dd_id = _parse_asdm_id(row.findtext('dataDescriptionId'))
        spw_id = _parse_asdm_id(row.findtext('spectralWindowId'))
        dd_spw[dd_id] = spw_id
    return dd_spw


def _parse_cfg_dds(xml_path: str) -> dict:
    """Parse ConfigDescription.xml and return {cfg_id: set_of_dd_ids}."""
    _require_file(xml_path)
    cfg_dds: dict = {}
    for row in ET.parse(xml_path).findall('row'):
        cfg_id = _parse_asdm_id(row.findtext('configDescriptionId'))
        dd_ids = _parse_asdm_id_array(row.findtext('dataDescriptionId'))
        cfg_dds[cfg_id] = set(dd_ids)
    return cfg_dds


def _parse_main_scan_cfgs(xml_path: str) -> dict:
    """Parse Main.xml and return {(eb_id, scan_num): set_of_cfg_ids}.

    Multiple rows may exist for the same (eb_id, scan_num) pair due to
    subscans; all referenced configDescriptionIds are collected.
    """
    _require_file(xml_path)
    scan_cfgs: dict = defaultdict(set)
    for row in ET.parse(xml_path).findall('row'):
        eb_id = _parse_asdm_id(row.findtext('execBlockId'))
        scan_num = int(row.findtext('scanNumber') or 0)
        cfg_id = _parse_asdm_id(row.findtext('configDescriptionId'))
        scan_cfgs[(eb_id, scan_num)].add(cfg_id)
    return dict(scan_cfgs)


def _parse_scan_list(xml_path: str) -> list:
    """Parse Scan.xml and return [(eb_id, scan_num), ...] in document order."""
    _require_file(xml_path)
    scans = []
    seen: set = set()
    for row in ET.parse(xml_path).findall('row'):
        eb_id = _parse_asdm_id(row.findtext('execBlockId'))
        scan_num = int(row.findtext('scanNumber') or 0)
        key = (eb_id, scan_num)
        if key not in seen:
            scans.append(key)
            seen.add(key)
    return scans


# ---------------------------------------------------------------------------
# Band determination helpers (private)
# ---------------------------------------------------------------------------

def _freq_to_vla_band(freq_hz: float) -> str:
    """Return the VLA band letter for *freq_hz* (Hz), or ``'unknown'``."""
    i = bisect.bisect_left(_VLA_BAND_LIMITS, freq_hz)
    letter = _VLA_BAND_LETTERS[i]
    return 'unknown' if letter == '?' else letter


def _vla_band_from_spw_name(name: str) -> str | None:
    """Extract the VLA band letter from an EVLA SPW name.

    EVLA spectral window names follow the pattern ``EVLA_<BAND>#<baseband>#<sub>``,
    e.g. ``EVLA_K#A0C0#0``.  Returns ``None`` if the name does not match.
    """
    if not name.startswith('EVLA_'):
        return None
    rest = name[5:]          # drop 'EVLA_'
    band = rest.split('#')[0]
    return band if band else None


# ---------------------------------------------------------------------------
# Range formatting helper (private)
# ---------------------------------------------------------------------------

def _ints_to_range_str(numbers: list) -> str:
    """Convert a list of integers to a compact range string.

    Examples:
        [1, 2, 3, 5, 7, 8, 9]  ->  '1~3,5,7~9'
        [4]                     ->  '4'
    """
    if not numbers:
        return ''
    nums = sorted(set(numbers))
    ranges = []
    start = end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append(f'{start}~{end}' if end > start else str(start))
            start = end = n
    ranges.append(f'{start}~{end}' if end > start else str(start))
    return ','.join(ranges)


# ---------------------------------------------------------------------------
# XML utility helpers (private)
# ---------------------------------------------------------------------------

def _require_file(path: str) -> None:
    """Raise FileNotFoundError if *path* does not exist."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f'Required ASDM table not found: {path}')


def _parse_asdm_id(id_str) -> int:
    """Parse an ASDM entity ID string such as ``'ExecBlock_3'`` -> ``3``."""
    if id_str is None:
        raise ValueError('Missing ID element in ASDM XML')
    _, _, suffix = id_str.strip().rpartition('_')
    if not suffix.isdigit():
        raise ValueError(f'Cannot parse integer ID from: {id_str!r}')
    return int(suffix)


def _parse_asdm_id_array(text) -> list:
    """Parse an ASDM array-encoded ID list.

    ASDM array fields are encoded as ``'ndims size1 [size2 ...] id1 id2 ...'``.
    For example::

        '1 8 DataDescription_0 DataDescription_1 ... DataDescription_7'

    Returns the list of integer IDs extracted from the ``Name_N`` tokens.
    """
    if not text:
        return []
    return [_parse_asdm_id(token) for token in text.split() if '_' in token]
