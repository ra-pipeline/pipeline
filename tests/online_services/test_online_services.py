"""Regression tests for ALMA pipeline online services.

These tests verify availability and correctness of three online services used
by the ALMA pipeline:

1. ALMA Flux Calibration Service (sc/flux)
   - Primary:  https://almascience.org/sc/flux
   - Backup:   https://asa.alma.cl/sc/flux

2. Jy/K Conversion Factor Service (jy-kelvins)
   - JAO (primary): https://asa.alma.cl/science/jy-kelvins
   - EA mirror:     https://almascience.nao.ac.jp/science/jy-kelvins
   - NA mirror:     https://almascience.nrao.edu/science/jy-kelvins
   - EU mirror:     https://almascience.eso.org/science/jy-kelvins

3. Antenna Position Corrections Service (uncertainties-service)
   - https://asa.alma.cl/uncertainties-service/uncertainties/versions/last/measurements/casa/

No pipeline package dependency is required; only stdlib + certifi are used.

Run with:
    python -m pytest test_online_services.py -v
or (from the pipeline repo root, bypassing the CASA-dependent conftest):
    python -m pytest tests/online_services/test_online_services.py --noconftest -v
"""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from xml.dom import minidom

import certifi
import functools
import pytest

# ===========================================================================
# Reference values
# (obtained by running the live services; fixed historical queries that will
# never change because they reference past observations / fixed dates)
# ===========================================================================

# Flux service: J1427-4206 on 27-March-2013 at 87 GHz
# Source: queried from asa.alma.cl/sc/flux on 2026-07-30
FLUX_REF_J1427_DENSITY: float = 7.7245263249054075   # Jy
FLUX_REF_J1427_SPIX: float = -0.359656945792801
FLUX_REF_TOLERANCE: float = 1e-3   # relative tolerance for floating-point comparison

# Jy/K service: uid://A002/X85c183/X36f  (hsd_calimage regression dataset)
# Source: queried from asa.alma.cl/science/jy-kelvins on 2026-07-30
# 3 antennas (DA61, PM03, PM04) × 4 SPWs → 12 entries total
JYPERK_REF_FACTOR_COUNT: int = 12
JYPERK_REF_FACTORS: dict[int, float] = {
    17: 43.768,
    19: 43.776,
    21: 43.824,
    23: 43.834,
}
JYPERK_REF_ANTENNAS: set[str] = {'DA61', 'PM03', 'PM04'}

# Antenna position service: uid://A002/Xc46ab2/X15ae  (PPR regression dataset)
# Source: queried from asa.alma.cl/uncertainties-service on 2026-07-30
# Returns a dict  {antenna_name: [X_ITRF, Y_ITRF, Z_ITRF]}  (metres)
# Note: the total number of antennas with corrections can grow as the service
# is updated; only the coordinates of a stable reference antenna are checked.
ANTPOS_REF_UID = 'uid://A002/Xc46ab2/X15ae'
ANTPOS_REF_CM05_XYZ: tuple[float, float, float] = (
    2225063.5458056196,
    -5440128.204003837,
    -2481550.0793935717,
)

# ---------------------------------------------------------------------------
# Shared SSL context
# ---------------------------------------------------------------------------

def _ssl_ctx() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


@functools.lru_cache(maxsize=None)
def _get(url: str, timeout: float = 60.0) -> bytes:
    """Perform an HTTPS GET and return the raw response body.

    Responses are cached for the duration of the test session so each unique
    URL is fetched exactly once, regardless of how many tests use it.
    """
    ctx = _ssl_ctx()
    with urllib.request.urlopen(url, context=ctx, timeout=timeout) as resp:
        return resp.read()


# ===========================================================================
# Service 1: ALMA Flux Calibration Service  (sc/flux)
# ===========================================================================
# The pipeline uses this "standard candle" test query to check liveness before
# a real observation query (see almaimportdata.py line ~207):
#   NAME=J1427-4206  DATE=27-March-2013  FREQUENCY=86837309056.169… Hz
# Source J1427-4206 at Band 3 is a well-known bright calibrator that has been
# measured continuously for decades, so its flux entry is stable.

FLUX_SERVICE_PRIMARY = 'https://almascience.org/sc/flux'
FLUX_SERVICE_BACKUP = 'https://asa.alma.cl/sc/flux'

FLUX_LIVENESS_PARAMS = {
    'NAME': 'J1427-4206',
    'DATE': '27-March-2013',
    'FREQUENCY': '86837309056.169219970703125',
    'WEIGHTED': 'true',
    'RESULT': '1',
    'VERBOSE': '1',
    'CATALOGUE': '5',
}

# Real-query example from testing logs (Band 6, 2023 dataset):
FLUX_REAL_PARAMS = {
    'NAME': 'J1957-3845',
    'DATE': '14-August-2023',
    'FREQUENCY': '224000001907.3486328125',
    'WEIGHTED': 'true',
    'RESULT': '1',
    'VERBOSE': '1',
    'CATALOGUE': '5',
}

# Fields we expect the service to return for a successful measurement
FLUX_EXPECTED_FIELD_NAMES = {
    'SourceName', 'FluxDensity', 'SpectralIndex',
    'Date', 'Frequency', 'StatusCode',
}


def _query_flux_service(base_url: str, params: dict[str, str]) -> dict[str, str | None]:
    """Query the sc/flux service and return a field-name→value dict."""
    url = f'{base_url}?{urllib.parse.urlencode(params)}'
    raw = _get(url)
    dom = minidom.parseString(raw)
    fields = dom.getElementsByTagName('FIELD')
    field_names = [f.getAttribute('name') for f in fields]
    rowdict: dict[str, str | None] = {}
    for node in dom.getElementsByTagName('TR'):
        cells = node.getElementsByTagName('TD')
        for name, cell in zip(field_names, cells):
            rowdict[name] = cell.childNodes[0].nodeValue if cell.childNodes else None
    return rowdict


class TestFluxService:
    """Tests for the ALMA source-flux catalogue service."""

    @pytest.mark.parametrize('base_url', [FLUX_SERVICE_PRIMARY, FLUX_SERVICE_BACKUP])
    def test_liveness(self, base_url: str) -> None:
        """Service responds with valid XML containing at least one FIELD element."""
        url = f'{base_url}?{urllib.parse.urlencode(FLUX_LIVENESS_PARAMS)}'
        raw = _get(url)
        assert raw, 'Empty response body'
        dom = minidom.parseString(raw)
        fields = dom.getElementsByTagName('FIELD')
        assert len(fields) > 0, f'No FIELD elements in response from {base_url}'

    @pytest.mark.parametrize('base_url', [FLUX_SERVICE_PRIMARY, FLUX_SERVICE_BACKUP])
    def test_known_source_liveness_query(self, base_url: str) -> None:
        """J1427-4206 on 27-March-2013 at 87 GHz returns a valid flux density."""
        result = _query_flux_service(base_url, FLUX_LIVENESS_PARAMS)
        assert result, 'No data rows returned'
        assert 'FluxDensity' in result, 'FluxDensity field missing'
        flux = result.get('FluxDensity')
        assert flux is not None, 'FluxDensity value is None'
        assert float(flux) > 0.0, f'Expected positive flux density, got {flux}'

    @pytest.mark.parametrize('base_url', [FLUX_SERVICE_PRIMARY, FLUX_SERVICE_BACKUP])
    def test_response_fields_present(self, base_url: str) -> None:
        """All expected XML field names are present in the response schema."""
        url = f'{base_url}?{urllib.parse.urlencode(FLUX_LIVENESS_PARAMS)}'
        raw = _get(url)
        dom = minidom.parseString(raw)
        returned_fields = {f.getAttribute('name') for f in dom.getElementsByTagName('FIELD')}
        missing = FLUX_EXPECTED_FIELD_NAMES - returned_fields
        assert not missing, f'Missing fields in response: {missing}'

    @pytest.mark.parametrize('base_url', [FLUX_SERVICE_PRIMARY, FLUX_SERVICE_BACKUP])
    def test_real_observation_query(self, base_url: str) -> None:
        """J1957-3845 on 14-August-2023 at Band 6 returns a plausible flux density."""
        result = _query_flux_service(base_url, FLUX_REAL_PARAMS)
        assert result, 'No data rows returned'
        flux_str = result.get('FluxDensity')
        assert flux_str is not None, 'FluxDensity is missing or None'
        flux = float(flux_str)
        assert 0.0 < flux < 100.0, f'Flux density out of plausible range (0, 100 Jy): {flux}'

    @pytest.mark.parametrize('base_url', [FLUX_SERVICE_PRIMARY, FLUX_SERVICE_BACKUP])
    def test_spectral_index_numeric(self, base_url: str) -> None:
        """SpectralIndex returned for the liveness source is a finite number."""
        result = _query_flux_service(base_url, FLUX_LIVENESS_PARAMS)
        spix_str = result.get('SpectralIndex')
        assert spix_str is not None, 'SpectralIndex missing'
        spix = float(spix_str)
        assert -5.0 < spix < 5.0, f'Spectral index unrealistically large: {spix}'

    @pytest.mark.parametrize('base_url', [FLUX_SERVICE_PRIMARY, FLUX_SERVICE_BACKUP])
    def test_source_name_echo(self, base_url: str) -> None:
        """Service echoes back the source name in the SourceName field."""
        result = _query_flux_service(base_url, FLUX_LIVENESS_PARAMS)
        source_name = result.get('SourceName', '')
        assert source_name, 'SourceName is empty'
        # The service may normalise the name; at minimum it should be non-empty
        assert len(source_name) > 0

    @pytest.mark.parametrize('base_url', [FLUX_SERVICE_PRIMARY, FLUX_SERVICE_BACKUP])
    def test_reference_flux_values(self, base_url: str) -> None:
        """J1427-4206 / 27-March-2013 / 87 GHz returns the known reference flux and spix.

        These are fixed historical values: the date and source are in the past so the
        service result will never change.  Tolerance is 0.1% relative.
        """
        result = _query_flux_service(base_url, FLUX_LIVENESS_PARAMS)
        flux = float(result['FluxDensity'])
        spix = float(result['SpectralIndex'])
        rel_flux_err = abs(flux - FLUX_REF_J1427_DENSITY) / FLUX_REF_J1427_DENSITY
        assert rel_flux_err < FLUX_REF_TOLERANCE, (
            f'FluxDensity {flux} differs from reference {FLUX_REF_J1427_DENSITY} '
            f'by {rel_flux_err:.2e} (tol {FLUX_REF_TOLERANCE})'
        )
        assert abs(spix - FLUX_REF_J1427_SPIX) < 1e-6, (
            f'SpectralIndex {spix} differs from reference {FLUX_REF_J1427_SPIX}'
        )


# ===========================================================================
# Service 2: Jy/K Conversion Factor Service  (jy-kelvins)
# ===========================================================================
# The pipeline calls:
#   <base>/asdm/?uid=<url-encoded UID>
# Example from testing log (hsd_calimage run):
#   https://asa.alma.cl/science/jy-kelvins/asdm/?uid=uid%3A%2F%2FA002%2FX85c183%2FX36f
# ASDM uid://A002/X85c183/X36f is a Single-Dish science dataset used in the
# hsd_calimage regression test.

JYPERK_ENDPOINTS = {
    'JAO (asa.alma.cl)':         'https://asa.alma.cl/science/jy-kelvins',
    'EA (almascience.nao.ac.jp)': 'https://almascience.nao.ac.jp/science/jy-kelvins',
    'NA (almascience.nrao.edu)':  'https://almascience.nrao.edu/science/jy-kelvins',
    'EU (almascience.eso.org)':   'https://almascience.eso.org/science/jy-kelvins',
}

# UID from hsd_calimage regression test (seen in getjyperkalma log)
JYPERK_TEST_UID = 'uid://A002/X85c183/X36f'


def _jyperk_url(base: str, uid: str, endpoint: str = 'asdm') -> str:
    encoded_uid = urllib.parse.quote(uid, safe='')
    return f'{base}/{endpoint}/?uid={encoded_uid}'


def _parse_jyperk_response(raw: bytes) -> list[dict]:
    """Parse JSON response from jy-kelvins service.

    The service returns JSON with the structure::

        {
          "success": true,
          "data": {
            "length": <int>,
            "factors": [
              {"MS": "...", "Antenna": "DA61", "Spwid": 17,
               "Polarization": "Polarization_0", "factor": 43.768},
              ...
            ]
          }
        }
    """
    payload = json.loads(raw)
    return payload.get('data', {}).get('factors', [])


class TestJyPerKService:
    """Tests for the ALMA Jy/K conversion factor database service."""

    @pytest.mark.parametrize('label,base_url', list(JYPERK_ENDPOINTS.items()))
    def test_liveness(self, label: str, base_url: str) -> None:
        """Service responds with HTTP 200 and non-empty body."""
        url = _jyperk_url(base_url, JYPERK_TEST_UID)
        raw = _get(url, timeout=60.0)
        assert raw, f'{label}: empty response body from {url}'

    @pytest.mark.parametrize('label,base_url', list(JYPERK_ENDPOINTS.items()))
    def test_json_format(self, label: str, base_url: str) -> None:
        """Response is valid JSON with a data.factors list."""
        url = _jyperk_url(base_url, JYPERK_TEST_UID)
        raw = _get(url, timeout=60.0)
        payload = json.loads(raw)
        assert payload.get('success') is True, f'{label}: success field is not True'
        rows = payload.get('data', {}).get('factors', [])
        assert len(rows) > 0, (
            f'{label}: no factor entries in data.factors from {url}'
        )

    @pytest.mark.parametrize('label,base_url', list(JYPERK_ENDPOINTS.items()))
    def test_factor_values_positive(self, label: str, base_url: str) -> None:
        """All Jy/K factor values are positive numbers."""
        url = _jyperk_url(base_url, JYPERK_TEST_UID)
        raw = _get(url, timeout=60.0)
        rows = _parse_jyperk_response(raw)
        assert rows, f'{label}: no rows to validate'
        for row in rows:
            factor = float(row['factor'])
            assert factor > 0.0, f'{label}: non-positive Jy/K factor: {row}'

    @pytest.mark.parametrize('label,base_url', list(JYPERK_ENDPOINTS.items()))
    def test_uid_in_response(self, label: str, base_url: str) -> None:
        """The UID queried appears in the MS field of the returned factors."""
        url = _jyperk_url(base_url, JYPERK_TEST_UID)
        raw = _get(url, timeout=60.0)
        rows = _parse_jyperk_response(raw)
        assert rows, f'{label}: no rows returned'
        uid_fragment = 'X85c183'  # part of the UID that should appear in MS name
        ms_values = [r['MS'] for r in rows]
        assert any(uid_fragment in ms for ms in ms_values), (
            f'{label}: UID fragment "{uid_fragment}" not found in MS field: {ms_values[:3]}'
        )

    @pytest.mark.parametrize('label,base_url', list(JYPERK_ENDPOINTS.items()))
    def test_polarizations_known(self, label: str, base_url: str) -> None:
        """All Polarization labels follow the expected Polarization_N pattern."""
        url = _jyperk_url(base_url, JYPERK_TEST_UID)
        raw = _get(url, timeout=60.0)
        rows = _parse_jyperk_response(raw)
        for row in rows:
            pol = row['Polarization']
            assert pol.startswith('Polarization_'), (
                f'{label}: unexpected polarization "{pol}" in row {row}'
            )

    @pytest.mark.parametrize('label,base_url', list(JYPERK_ENDPOINTS.items()))
    def test_reference_factor_values(self, label: str, base_url: str) -> None:
        """Jy/K factors for uid://A002/X85c183/X36f match reference values (tol 0.1%)."""
        url = _jyperk_url(base_url, JYPERK_TEST_UID)
        raw = _get(url, timeout=60.0)
        rows = _parse_jyperk_response(raw)
        assert len(rows) == JYPERK_REF_FACTOR_COUNT, (
            f'{label}: expected {JYPERK_REF_FACTOR_COUNT} factor entries, got {len(rows)}'
        )
        returned_antennas = {r['Antenna'] for r in rows}
        assert returned_antennas == JYPERK_REF_ANTENNAS, (
            f'{label}: antenna set mismatch – expected {JYPERK_REF_ANTENNAS}, got {returned_antennas}'
        )
        for row in rows:
            spw = int(row['Spwid'])
            if spw in JYPERK_REF_FACTORS:
                ref = JYPERK_REF_FACTORS[spw]
                got = float(row['factor'])
                rel_err = abs(got - ref) / ref
                assert rel_err < FLUX_REF_TOLERANCE, (
                    f'{label}: Spw {spw} factor {got} differs from reference {ref} '
                    f'by {rel_err:.2e} (tol {FLUX_REF_TOLERANCE})'
                )


# ===========================================================================
# Service 3: Antenna Position Correction Service  (uncertainties-service)
# ===========================================================================
# The pipeline calls:
#   <base>/?asdm=<encoded_uid>&search=auto&firstIntegration=True
# Example from testing log (uid___A002_Xc46ab2_X15ae PPR run):
#   https://asa.alma.cl/uncertainties-service/.../casa//?asdm=uid%3A%2F%2FA002%2FXc46ab2%2FX15ae&search=auto&firstIntegration=True
# Returns JSON.

ANTPOS_SERVICE_BASE = (
    'https://asa.alma.cl/uncertainties-service/uncertainties/'
    'versions/last/measurements/casa/'
)

# UID from the PPR regression test that successfully queried the service
ANTPOS_TEST_UID = 'uid://A002/Xc46ab2/X15ae'

# Known no-correction UID (the service returned quickly with an empty list for
# newer short EBs; use a historical UID that is known to have corrections)
ANTPOS_KNOWN_UID_WITH_CORRECTIONS = 'uid://A002/Xc46ab2/X15ae'


def _antpos_url(uid: str, search: str = 'auto', first_integration: bool = True) -> str:
    params = urllib.parse.urlencode({
        'asdm': uid,
        'search': search,
        'firstIntegration': str(first_integration),
    })
    return f'{ANTPOS_SERVICE_BASE}?{params}'


def _query_antpos(uid: str) -> list | dict:
    """Query the antenna position service and return the parsed JSON."""
    url = _antpos_url(uid)
    raw = _get(url, timeout=60.0)
    return json.loads(raw)


class TestAntposService:
    """Tests for the ALMA antenna position corrections service."""

    def test_liveness(self) -> None:
        """Service responds with HTTP 200 for a known ASDM UID."""
        url = _antpos_url(ANTPOS_TEST_UID)
        raw = _get(url, timeout=60.0)
        assert raw, f'Empty response body from {url}'

    def test_response_is_valid_json(self) -> None:
        """Response body is parseable as JSON dict."""
        url = _antpos_url(ANTPOS_TEST_UID)
        raw = _get(url, timeout=60.0)
        data = json.loads(raw)  # raises on invalid JSON
        assert isinstance(data, dict)

    def test_response_is_dict(self) -> None:
        """JSON response is a dict mapping antenna names to [X, Y, Z] lists."""
        data = _query_antpos(ANTPOS_TEST_UID)
        assert isinstance(data, dict), (
            f'Expected dict, got {type(data).__name__}'
        )

    def test_response_schema(self) -> None:
        """Response is a dict mapping antenna names to [X, Y, Z] lists (ITRF metres)."""
        data = _query_antpos(ANTPOS_TEST_UID)
        assert isinstance(data, dict), f'Expected dict, got {type(data).__name__}'
        if not data:
            pytest.skip('No antenna position corrections returned for this UID')
        for ant_name, xyz in data.items():
            assert isinstance(ant_name, str), f'Antenna key is not a string: {ant_name!r}'
            assert isinstance(xyz, list) and len(xyz) == 3, (
                f'Expected [X, Y, Z] list for antenna {ant_name}, got {xyz!r}'
            )

    def test_coordinate_values_are_finite(self) -> None:
        """All ITRF coordinate values are finite floats."""
        import math
        data = _query_antpos(ANTPOS_TEST_UID)
        if not data:
            pytest.skip('No antenna position corrections for this UID')
        for ant_name, xyz in data.items():
            for i, val in enumerate(xyz):
                assert math.isfinite(float(val)), (
                    f'Non-finite coordinate [{i}] for antenna {ant_name}: {val}'
                )

    def test_reference_values(self) -> None:
        """uid://A002/Xc46ab2/X15ae: CM05 ITRF position matches reference (tol 1 mm)."""
        data = _query_antpos(ANTPOS_REF_UID)
        assert isinstance(data, dict), f'Expected dict, got {type(data).__name__}'
        assert len(data) >= 1, 'No antenna corrections returned'
        assert 'CM05' in data, f'Reference antenna CM05 missing; got {list(data)}'
        x, y, z = data['CM05']
        rx, ry, rz = ANTPOS_REF_CM05_XYZ
        tol_m = 1e-3   # 1 mm
        assert abs(x - rx) < tol_m, f'CM05 X: {x} vs ref {rx}'
        assert abs(y - ry) < tol_m, f'CM05 Y: {y} vs ref {ry}'
        assert abs(z - rz) < tol_m, f'CM05 Z: {z} vs ref {rz}'

    def test_search_auto_parameter(self) -> None:
        """search=auto parameter is accepted without error."""
        url = _antpos_url(ANTPOS_TEST_UID, search='auto')
        raw = _get(url, timeout=60.0)
        assert raw, 'Empty response with search=auto'

    def test_search_both_latest_parameter(self) -> None:
        """search=both_latest parameter is accepted without error."""
        url = _antpos_url(ANTPOS_TEST_UID, search='both_latest')
        raw = _get(url, timeout=60.0)
        assert raw, 'Empty response with search=both_latest'

    def test_search_both_closest_parameter(self) -> None:
        """search=both_closest parameter is accepted without error."""
        url = _antpos_url(ANTPOS_TEST_UID, search='both_closest')
        raw = _get(url, timeout=60.0)
        assert raw, 'Empty response with search=both_closest'

    def test_multiple_uids(self) -> None:
        """Several UIDs seen in regression test logs all return valid JSON dicts."""
        # UIDs observed in testing logs for various datasets
        test_uids = [
            'uid://A002/Xc46ab2/X15ae',
            'uid://A002/X1199f9e/X7c24',
            'uid://A002/Xd0a588/X2239',
            'uid://A002/Xee1eb6/Xc58d',
        ]
        for uid in test_uids:
            url = _antpos_url(uid)
            raw = _get(url, timeout=60.0)
            data = json.loads(raw)
            assert isinstance(data, dict), f'Expected dict for UID {uid}, got {type(data).__name__}'


# ===========================================================================
# Cross-service / smoke tests
# ===========================================================================

class TestServiceAvailability:
    """Quick availability smoke tests to confirm all service roots respond."""

    @pytest.mark.parametrize('name,url', [
        ('Flux primary', FLUX_SERVICE_PRIMARY),
        ('Flux backup', FLUX_SERVICE_BACKUP),
        ('JyPerK JAO', 'https://asa.alma.cl/science/jy-kelvins'),
        ('JyPerK EA', 'https://almascience.nao.ac.jp/science/jy-kelvins'),
        ('JyPerK NA', 'https://almascience.nrao.edu/science/jy-kelvins'),
        ('JyPerK EU', 'https://almascience.eso.org/science/jy-kelvins'),
        ('Antpos', ANTPOS_SERVICE_BASE),
    ])
    def test_service_reachable(self, name: str, url: str) -> None:
        """Each service root/base URL returns a non-error HTTP response."""
        ctx = _ssl_ctx()
        try:
            with urllib.request.urlopen(url, context=ctx, timeout=30.0) as resp:
                # Any 2xx/3xx/4xx is acceptable here – we just want to confirm
                # the server is up and TLS works.  A 404 on the bare root is
                # fine; the real queries use specific paths.
                assert resp is not None, f'{name}: no response object'
        except urllib.error.HTTPError as exc:
            # HTTPError means the server responded – that's enough for a
            # reachability check (e.g. 404 on a bare root URL is acceptable).
            assert exc.code < 500, f'{name}: server error {exc.code} from {url}'
