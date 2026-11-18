"""Retrieve catalogue fluxes with bounded retries and endpoint failover."""

from __future__ import annotations

import collections
import datetime
import decimal
import ssl
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.client import IncompleteRead
from typing import TYPE_CHECKING, Any
from xml.dom import minidom
from xml.parsers.expat import ExpatError

import certifi

from pipeline import domain, infrastructure
from pipeline.domain import measures
from pipeline.h.tasks.common import commonfluxresults
from pipeline.h.tasks.importdata import fluxes
from pipeline.infrastructure import utils

if TYPE_CHECKING:
    from pipeline.domain import FluxMeasurement, MeasurementSet, Source, SpectralWindow
    from pipeline.h.tasks.common.commonfluxresults import FluxCalibrationResults

LOG = infrastructure.logging.get_logger(__name__)
ORIGIN_DB = 'DB'
FLUX_SERVICE_URL = 'https://almascience.org/sc/flux'
FLUX_SERVICE_URL_BACKUP = 'https://asa.alma.cl/sc/flux'
TEST_OBS_TIME = datetime.datetime(2013, 3, 27, 7, 53, 3, 168000, tzinfo=datetime.timezone.utc)
TEST_FREQ_HZ = '86837309056.169219970703125'
TEST_SOURCENAME = 'J1427-4206'
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': '*/*',
}
RETRYABLE_HTTP_CODES = frozenset({408, 429, 500, 502, 503, 504})


class FluxServiceResponseError(ValueError):
    """The service returned XML without a usable catalogue response structure."""


class FluxServiceClient:
    """Share the selected flux endpoint across queries in one import."""

    def __init__(self, service_url: str | None = None) -> None:
        """Initialize endpoint selection without making a probe request.

        Args:
            service_url: Selected endpoint, or the configured primary when omitted.
        """
        primary_url, backup_url = get_flux_urls()
        self.service_url: str = primary_url if service_url is None else service_url
        self._backup_url: str | None = (
            backup_url if self.service_url == primary_url and backup_url != primary_url else None
        )
        self._status: str = 'BACKUPURL' if self.service_url == backup_url and backup_url != primary_url else 'FIRSTURL'

    @property
    def status(self) -> str:
        """QA service status for the current endpoint."""
        return self._status

    def query(self, obs_time: datetime.datetime, frequency: str, sourcename: str) -> dict[str, str | None]:
        """Query the selected service and retain a successful backup endpoint.

        Args:
            obs_time: Observation date.
            frequency: Query frequency in Hz.
            sourcename: Source name.

        Returns:
            The catalogue response from the working endpoint.

        Raises:
            OSError: If the available endpoints cannot be reached.
            IncompleteRead: If the available endpoints return truncated responses.
            ExpatError: If the available endpoints return malformed XML.
            FluxServiceResponseError: If the available endpoints return unusable catalogue structures.
        """
        try:
            return fluxservice(self.service_url, obs_time, frequency, sourcename)
        except (OSError, IncompleteRead, ExpatError, FluxServiceResponseError):
            if self._backup_url is None:
                raise
            LOG.warning('Flux query failed at %s; trying backup %s.', self.service_url, self._backup_url)
            result = fluxservice(self._backup_url, obs_time, frequency, sourcename)
            self.service_url = self._backup_url
            self._backup_url = None
            self._status = 'BACKUPURL'
            return result


def get_flux_urls() -> tuple[str, str]:
    """Returns the primary and backup flux service URLs."""
    flux_url = utils.get_valid_url('FLUX_SERVICE_URL', FLUX_SERVICE_URL)
    backup_flux_url = utils.get_valid_url('FLUX_SERVICE_URL_BACKUP', FLUX_SERVICE_URL_BACKUP)
    return flux_url, backup_flux_url


def check_service() -> tuple[str, str | None]:
    """Test the flux catalogue service URLs (primary then backup) using a test query.

    Returns:
        tuple of (status, service_url)
        where status is 'FIRSTURL', 'BACKUPURL', or 'FAIL',
        and service_url is the working URL (or None if 'FAIL').
    """
    flux_url, backup_flux_url = get_flux_urls()

    try:
        LOG.info('Attempting test query at primary flux service: %s', flux_url)
        fluxservice(flux_url, TEST_OBS_TIME, TEST_FREQ_HZ, TEST_SOURCENAME)
        return 'FIRSTURL', flux_url
    except Exception:
        LOG.warning('Unable to execute initial test query with primary flux service.')
        LOG.debug(traceback.format_exc())
        try:
            LOG.info('Attempting test query at backup flux service: %s', backup_flux_url)
            fluxservice(backup_flux_url, TEST_OBS_TIME, TEST_FREQ_HZ, TEST_SOURCENAME)
            return 'BACKUPURL', backup_flux_url
        except Exception:
            LOG.warning(
                'Unable to execute backup test query with flux service.\n'
                'Proceeding without using the online flux catalog service.'
            )
            LOG.debug(traceback.format_exc())
            return 'FAIL', None


def get_setjy_results(
    mses: list[MeasurementSet],
    service_url: str | None = None,
    *,
    client: FluxServiceClient | None = None,
) -> tuple[list[FluxCalibrationResults], list[dict[str, Any]]]:
    """Get flux values from the database service, falling back to the Source table XML.

    Args:
        mses: Measurement sets for which to retrieve flux values.
        service_url: Flux service URL to query. The configured primary URL is used when this is ``None``.
        client: Shared endpoint selection for this import; takes precedence over service_url.

    Returns:
        Flux calibration results and any QA status entries returned by the service.
    """
    if client is None:
        client = FluxServiceClient(service_url)

    results = []
    qastatus = []
    for ms in mses:
        result = commonfluxresults.FluxCalibrationResults(ms.name)
        science_spw_ids = {spw.id for spw in ms.get_spectral_windows()}

        fluxdb_results, qacodes = read_fluxes_db(ms, client=client)

        for source, measurements in fluxdb_results.items():
            m = [m for m in measurements if int(m.spw_id) in science_spw_ids]

            # import flux values for all fields and intents so that we can
            # compare them to the fluxscale-derived values later in the run
            #            for field in [f for f in source.fields if 'AMPLITUDE' in f.intents]:
            for field in source.fields:
                result.measurements[field.id].extend(m)

        results.append(result)
        if qacodes:
            qastatus.extend(qacodes)

    return results, qastatus


def read_fluxes_db(
    ms: MeasurementSet,
    service_url: str | None = None,
    *,
    client: FluxServiceClient | None = None,
) -> tuple[collections.defaultdict[Source, list[FluxMeasurement]], list[dict[str, Any]] | None]:
    """Read fluxes from the database server, defaulting to the Source XML table when necessary.

    Args:
        ms: Measurement set for which to retrieve flux values.
        service_url: Flux service URL to query. The configured primary URL is used when this is ``None``.
        client: Shared endpoint selection; takes precedence over service_url.

    Returns:
        Flux measurements grouped by source and any QA status entries returned by the service.
    """
    if client is None:
        client = FluxServiceClient(service_url)

    xml_measurements = fluxes.read_fluxes_nodb(ms)

    if not xml_measurements:
        # Source.xml could not be read or parsed. Fall back to catalogue query
        return flux_nosourcexml(ms, client=client), None

    results, qacodes = add_catalogue_fluxes(xml_measurements, ms, client=client)

    return results, qacodes


def flux_nosourcexml(
    ms: MeasurementSet,
    service_url: str | None = None,
    *,
    client: FluxServiceClient | None = None,
) -> collections.defaultdict[Source, list[FluxMeasurement]]:
    """Query the flux service using frequencies from a measurement set without Source.xml.

    Args:
        ms: Measurement set for which to retrieve flux values.
        service_url: Flux service URL to query. The configured primary URL is used when this is ``None``.
        client: Shared endpoint selection; takes precedence over service_url.

    Returns:
        Flux measurements grouped by source.
    """
    result = collections.defaultdict(list)
    if client is None:
        client = FluxServiceClient(service_url)

    for source in ms.sources:
        for spw in ms.get_spectral_windows(science_windows_only=True):
            url, version, status_code, data_conditions, clarification, catalogue_measurement = query_online_catalogue(
                client.service_url, ms, spw, source, client=client
            )
            if catalogue_measurement:
                result[source].append(catalogue_measurement)
                # set text for logging statements
                catalogue_I = catalogue_measurement.I
                spix = catalogue_measurement.spix
                age = catalogue_measurement.age

            else:
                # set text for logging statements
                catalogue_I = 'N/A'
                spix = 'N/A'
                age = 'N/A'

            log_result(
                source, spw, 'N/A', catalogue_I, spix, age, url, version, status_code, data_conditions, clarification
            )

    return result


def buildurl(service_url: str, obs_time: datetime.datetime, frequency: str, sourcename: str) -> str:
    """Construct a catalogue query URL for the source, date, and frequency."""
    # Example:
    # https://almascience.eso.org/sc/flux?DATE=10-August-2017&FREQUENCY=232101563000.0&NAME=J1924-2914&WEIGHTED=true&RESULT=1&CATALOGUE=5
    # New Example May 2019:
    # https://osf-sourcecat-2019apr.asa-test.alma.cl/sc/flux?DATE=27-March-2013&FREQUENCY=86837309056.169219970703125&WEIGHTED=true&RESULT=0&NAME=J1427-4206
    date = f'{str(obs_time.day).zfill(2)}-{obs_time.strftime("%B")}-{obs_time.year}'
    sourcename = sanitize_string(sourcename)
    urlparams = buildparams(sourcename, date, frequency)

    url = f'{service_url}?{urlparams}'
    LOG.debug('SC URL: %s', url)

    return url


def fluxservice(
    service_url: str,
    obs_time: datetime.datetime,
    frequency: str,
    sourcename: str,
    retries: int = 2,
    retry_delay: float = 0.5,
    headers: dict[str, str] | None = None,
) -> dict[str, str | None]:
    """Query the online flux catalogue service.

    Args:
        service_url: URL for the database service.
        obs_time: Observation time used to construct the query date.
        frequency: Query frequency in Hz.
        sourcename: Name of the source to query.
        retries: Number of times to retry the query after the initial attempt.
        retry_delay: Initial delay between attempts in seconds. The delay doubles after each failed attempt.
        headers: HTTP request headers. The default headers are used when this is ``None``.

    Returns:
        A dictionary containing the values returned by the flux catalogue service.

    Raises:
        OSError: If all attempts to contact or read from the service fail.
        IncompleteRead: If all attempts to read the full response fail.
        ExpatError: If the service response cannot be parsed as XML.
        FluxServiceResponseError: If the response has no catalogue row or an invalid status code.
        ValueError: If retries or retry_delay is negative.
    """
    if retries < 0 or retry_delay < 0:
        raise ValueError('retries and retry_delay must be nonnegative')
    url = buildurl(service_url, obs_time, frequency, sourcename)
    LOG.info('Attempting query %s', url)

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    request_headers = DEFAULT_HEADERS if headers is None else headers
    req = urllib.request.Request(url, headers=request_headers)

    content = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, context=ssl_context, timeout=60.0) as response:
                content = response.read()
            break
        except (OSError, IncompleteRead) as e:
            retryable = not isinstance(e, urllib.error.HTTPError) or e.code in RETRYABLE_HTTP_CODES
            reason = e.reason if isinstance(e, urllib.error.URLError) else e
            if isinstance(reason, ssl.SSLCertVerificationError):
                retryable = False
            if attempt >= retries or not retryable:
                LOG.warning('Problem contacting flux service at: <a href="%s">%s</a>', url, url)
                raise

            if isinstance(e, urllib.error.HTTPError):
                e.close()
            delay = retry_delay * (2**attempt)
            LOG.warning('Query attempt %d failed: %s. Retrying in %.1fs...', attempt + 1, e, delay)
            time.sleep(delay)

    try:
        dom = minidom.parseString(content)
    except ExpatError:
        LOG.warning('Could not parse source catalogue response')
        raise

    fields = dom.getElementsByTagName('FIELD')
    field_names = [field.getAttribute('name') for field in fields]
    output_fields = {
        'statuscode': 'StatusCode',
        'sourcename': 'SourceName',
        'dbfrequency': 'Frequency',
        'date': 'Date',
        'fluxdensity': 'FluxDensity',
        'fluxdensityerror': 'FluxDensityError',
        'spectralindex': 'SpectralIndex',
        'spectralindexerror': 'SpectralIndexError',
        'dataconditions': 'DataConditions',
        'ageOfNearestMonitorPoint': 'Nearest Measurement Date',
        'version': 'Version',
        'clarification': 'Clarification',
    }

    rowdict = {}
    for node in dom.getElementsByTagName('TR'):
        row = node.getElementsByTagName('TD')
        row_values = {
            field_name: cell.childNodes[0].nodeValue if cell.childNodes else None
            for field_name, cell in zip(field_names, row)
        }
        for output_key, field_name in output_fields.items():
            rowdict[output_key] = row_values.get(field_name)
        rowdict['url'] = url

    try:
        status_code = int(rowdict['statuscode'])
    except (KeyError, TypeError, ValueError) as exc:
        raise FluxServiceResponseError('Flux response has no catalogue row with a valid StatusCode') from exc
    if status_code not in range(5):
        raise FluxServiceResponseError(f'Unsupported flux catalogue StatusCode: {status_code}')
    if status_code != 4 and not {'FluxDensity', 'SpectralIndex'}.issubset(field_names):
        raise FluxServiceResponseError('Flux response is missing FluxDensity or SpectralIndex columns')
    rowdict['statuscode'] = str(status_code)
    return rowdict


def buildparams(name: str, date: str, frequency: str) -> str:
    """Encode the flux catalogue query parameters."""
    params = dict(NAME=name, DATE=date, FREQUENCY=frequency, WEIGHTED='true', RESULT=1, VERBOSE=1, CATALOGUE=5)
    return urllib.parse.urlencode(params)


def sanitize_string(name: str) -> str:
    """Sanitize source name if needed, taking first alias."""
    return name.split(';')[0]


def query_online_catalogue(
    flux_url: str,
    ms: MeasurementSet,
    spw: SpectralWindow,
    source: Source,
    *,
    client: FluxServiceClient | None = None,
) -> tuple[str, str | None, str, str | None, str | None, FluxMeasurement | None]:
    """Retrieve a catalogue measurement and its service metadata.

    Args:
        flux_url: Selected service URL when no client is supplied.
        ms: Measurement set providing the observation date.
        spw: Spectral window providing the query frequency.
        source: Source to query.
        client: Shared endpoint selection for this import.

    Returns:
        URL, version, status, data conditions, clarification, and optional flux measurement.
    """
    source_name = source.name
    freq_hz = str(spw.centre_frequency.to_units(measures.FrequencyUnits.HERTZ))
    obs_time = utils.get_epoch_as_datetime(ms.start_time)

    LOG.info('Input source name: %s    Input SPW: %s', str(source_name), str(spw.id))

    utcnow = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    try:
        if client is None:
            client = FluxServiceClient(flux_url)
        fluxdict = client.query(obs_time, freq_hz, source_name)
        flux_url = client.service_url
    except (OSError, IncompleteRead, ExpatError, FluxServiceResponseError) as exc:
        LOG.warning('Unable to retrieve catalogue flux for source %s spw %s: %s', source_name, spw.id, exc)
        # error contacting service
        return flux_url, '0.0', '0', None, None, None

    try:
        cat_fd = float(fluxdict['fluxdensity'])
        cat_spix = float(fluxdict['spectralindex'])
    except (TypeError, ValueError):
        # could not convert 'null' to number. Bad catalogue value.
        return flux_url, '0.0', fluxdict['statuscode'], None, fluxdict['clarification'], None

    valid_catalogue_val = cat_fd > 0.0 and cat_spix != -1000
    if not valid_catalogue_val:
        return flux_url, '0.0', fluxdict['statuscode'], None, fluxdict['clarification'], None

    final_I = measures.FluxDensity(cat_fd, measures.FluxDensityUnits.JANSKY)
    final_spix = decimal.Decimal('%0.3f' % cat_spix)
    age_n_m_p = fluxdict['ageOfNearestMonitorPoint']

    return (
        fluxdict['url'],
        fluxdict['version'],
        fluxdict['statuscode'],
        fluxdict['dataconditions'],
        fluxdict['clarification'],
        domain.FluxMeasurement(spw.id, final_I, spix=final_spix, origin=ORIGIN_DB, queried_at=utcnow, age=age_n_m_p),
    )


def add_catalogue_fluxes(
    measurements: collections.defaultdict[Source, list[FluxMeasurement]],
    ms: MeasurementSet,
    service_url: str | None = None,
    *,
    client: FluxServiceClient | None = None,
) -> tuple[collections.defaultdict[Source, list[FluxMeasurement]], list[dict[str, Any]]]:
    """Replace Source.xml measurements with available catalogue measurements.

    Args:
        measurements: Source.xml flux measurements grouped by source.
        ms: Measurement set associated with the measurements.
        service_url: Flux service URL to query. The configured primary URL is used when this is ``None``.
        client: Shared endpoint selection; takes precedence over service_url.

    Returns:
        Updated flux measurements grouped by source and any QA status entries returned by the service.
    """
    results = collections.defaultdict(list)
    qacodes = []  # Dictionaries will be added here for codes and warning messages from the sources catalog
    science_windows = ms.get_spectral_windows(science_windows_only=True)

    if client is None:
        client = FluxServiceClient(service_url)

    # Continue with required queries
    for source, xml_measurements in measurements.items():
        for xml_measurement in xml_measurements:
            spw = ms.get_spectral_window(xml_measurement.spw_id)

            # only query database for science windows
            if spw not in science_windows:
                continue

            url, version, status_code, data_conditions, clarification, catalogue_measurement = query_online_catalogue(
                client.service_url, ms, spw, source, client=client
            )

            if catalogue_measurement:
                # Catalogue doesn't return Q,U,V so adopt Q,U,V from XML
                catalogue_measurement.Q = xml_measurement.Q
                catalogue_measurement.U = xml_measurement.U
                catalogue_measurement.V = xml_measurement.V

                results[source].append(catalogue_measurement)

                # set text for logging statements
                catalogue_I = catalogue_measurement.I
                spix = catalogue_measurement.spix
                age = catalogue_measurement.age

            else:
                # No/invalid catalogue entry, so use Source.XML measurement
                results[source].append(xml_measurement)

                # set text for logging statements
                catalogue_I = 'N/A'
                spix = 'N/A'
                age = 'N/A'

            if clarification or int(status_code) > 1:
                qacodes.append({'source': source, 'status_code': status_code, 'clarification': clarification})

            log_result(
                source,
                spw,
                xml_measurement.I,
                catalogue_I,
                spix,
                age,
                url,
                version,
                status_code,
                data_conditions,
                clarification,
            )

    return results, qacodes


def log_result(
    source: Source,
    spw: SpectralWindow,
    asdm_I: str,
    catalogue_I: str,
    spix: str,
    age: str,
    url: str,
    version: str,
    status_code: str,
    data_conditions: str,
    clarification: str,
) -> None:
    """Log the adopted flux and the catalogue response metadata."""
    codedict = {}
    codedict[0] = 'Grid cal flux estimation heuristic used'
    codedict[1] = 'Low-cadence flux estimation heuristic used'
    codedict[2] = 'Flux densities outside of the window were required to calculate an answer'
    codedict[3] = 'Fallback algorithm used, went outside the window'
    codedict[4] = 'No valid flux density could be calculated'

    # DataConditions breakdown (3 digits historically, expanded to 4 digits in OFFLINE-2026AUG):
    # value[0]: number of available measurements used, where 9 means 9 or more
    # value[1]: 1 if measurements exist from at least two distinct bands, 0 otherwise
    # value[2]: 1 if there is at least one measurement on either side of the selected date, 0 otherwise
    # value[3]: for spectral index, 1 if a measurement in a band is bracketed in time by measurements in another
    #           band, 0 otherwise (see ICT-26895/ICT-27420)
    decision = {'0': 'No', '1': 'Yes'}

    LOG.info('Source: %s spw: %s    ASDM flux: %s    Catalogue flux: %s', source.name, spw.id, asdm_I, catalogue_I)
    LOG.info('         Online catalog Spectral Index: %s', spix)
    LOG.info('         ageOfNearestMonitorPoint: %s', age)
    LOG.info('         %s', codedict[int(status_code)])
    if data_conditions:
        dc_str = str(data_conditions)
        n_meas = '>= 9' if dc_str[0] == '9' else dc_str[0]
        multi_band = decision.get(dc_str[1], 'N/A') if len(dc_str) > 1 else 'N/A'
        date_bracketed = decision.get(dc_str[2], 'N/A') if len(dc_str) > 2 else 'N/A'
        spix_bracketed = decision.get(dc_str[3], 'N/A') if len(dc_str) > 3 else 'N/A'
        LOG.info('         Number of measurements = %s', n_meas)
        LOG.info('         Measurements in >= 2 distinct bands? %s', multi_band)
        LOG.info('         Observation date bracketed in time? %s', date_bracketed)
        LOG.info('         Spectral index cross-band bracketed in time? %s', spix_bracketed)
    else:
        LOG.info('         Number of measurements = N/A')
        LOG.info('         Measurements in >= 2 distinct bands? N/A')
        LOG.info('         Observation date bracketed in time? N/A')
        LOG.info('         Spectral index cross-band bracketed in time? N/A')

    LOG.info('         URL: %s', url)
    LOG.info('         Version: %s', version)
    if clarification:
        LOG.info('         WARNING message returned: %s', clarification)
    if catalogue_I == 'N/A':
        LOG.warning('No flux returned from the flux catalogue service for source %s spw %s.', source.name, spw.id)
    LOG.info('---------------------------------------------')
