from __future__ import annotations

import json
import os
import traceback
from typing import TYPE_CHECKING, Literal

import numpy as np

from pipeline import infrastructure
from pipeline.hif.tasks.antpos import antpos
from pipeline.hif.tasks.antpos.antpos import AntposResults
from pipeline.infrastructure import casa_tasks, casa_tools, exceptions, task_registry, utils, vdp

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context

__all__ = [
    'ALMAAntpos',
    'ALMAAntposInputs'
]

LOG = infrastructure.logging.get_logger(__name__)
ANTPOS_SERVICE_URL = ['https://asa.alma.cl/uncertainties-service/uncertainties/versions/last/measurements/casa/']


class ALMAAntposInputs(antpos.AntposInputs):
    """
    ALMAAntposInputs defines the inputs for the ALMAAntpos pipeline task.
    """
    # These are ALMA specific settings and override the defaults in
    # the base class.

    hm_antpos = vdp.VisDependentProperty(default='online')

    @vdp.VisDependentProperty
    def antposfile(self):
        return "antennapos.json"

    @antposfile.convert
    def antposfile(self, value):
        if not value and self.hm_antpos == 'online':
            value = "antennapos.json"
            LOG.info("Input parameter antposfile cannot be empty when hm_antpos='online', using antposfile=%s instead.", value)
        return value

    threshold = vdp.VisDependentProperty(default=1.0)
    snr = vdp.VisDependentProperty(default="default")
    search = vdp.VisDependentProperty(default='auto')

    def __init__(
            self,
            context: Context,
            output_dir: str | None = None,
            vis: list[str] | None = None,
            caltable: list[str] | None = None,
            hm_antpos: Literal['online', 'manual', 'file'] | None = None,
            antposfile: str | None = None,
            antenna: str | None = None,
            offsets: list[float] | None = None,
            threshold: float | None = None,
            snr: float | None = None,
            search: Literal['both_latest', 'both_closest'] | None = None,
            ):
        """
        Initializes the pipeline input parameters for antenna position corrections.

        Args:
            context: The pipeline execution context.

            output_dir: Directory where output files will be stored.
                Defaults to the current working directory.

            vis: List of input MeasurementSets.
                Defaults to those specified in the pipeline context.

                Example: ['ngc5921.ms']

            caltable: List of output calibration table names.
                Defaults to the standard pipeline naming convention.

                Example: ['ngc5921.gcal']

            hm_antpos: 
                - `'online'` : Query ALMA database through CASA task `getantposalma` or reuse 
                pre-existing queried/downloaded JSON files. Files follow the naming pattern 
                `{eb_name}.{antposfile}`. For multi-MS pipeline runs, the MS basename 
                is appended to the filename (e.g., `uid___A002_X123_X4567.antennapos.json`).
                - `'manual'` : Use user-provided corrections.
                - `'file'` : Load corrections from a single old-style CSV antenna position file.
                
                Example: 'manual'

            antposfile: 
                Path to a csv file containing antenna position offsets for `hm_antpos='file'` (required) or the name
                 of the outfile created by `getantposalma` for `hm_antpos='online'`. In order to work with multi-MS
                 pipeline runs, the MS basename will be appended to the file name when using `hm_antpos='online'` (i.e.
                 'uid___A002_X123_X4567.antennapos.json').

                Default: 'antennapos.json'                

            antenna: 
                A comma-separated string of antennas whose positions are to be corrected (if `hm_antpos` is 'manual' 
                or 'online').

                Example: 'DV05,DV07'

            offsets: 
                A flat list of floating-point offsets (X, Y, Z) for all specified antennas.
                The length of the list must be three times the number of antennas.

                Example (for two antennas): `[0.01, 0.02, 0.03, 0.03, 0.02, 0.01]`

            threshold: 
                Threshold value (in wavelengths) above which antenna position offsets are highlighted in the weblog.
                Defaults to 1.0.

                Example: 1.0

            snr:
                A float value describing the signal-to-noise threshold used by the getantposalma task. Antennas with 
                snr below the threshold will not be retrieved. Only used with `hm_antpos='online'`. Defaults to 'default'.

                Example: 5.0

            search:
                Search algorithm used by the getantposalma task. Supports 'both_latest', 'both_closest', and 'auto'.
                Only used with `hm_antpos='online'`. Defaults to 'auto'.

                Example: 'both_closest'
        """
        super().__init__(
            context,
            output_dir=output_dir,
            vis=vis,
            caltable=caltable,
            hm_antpos=hm_antpos,
            antposfile=antposfile,
            antenna=antenna,
            offsets=offsets
            )
        self.threshold = threshold
        self.snr = snr
        self.search = search

    def to_casa_args(self) -> dict[str, str | list[float]]:
        """Configure gencal task arguments and return them in dictionary format.

        Returns:
            vis: Name of the input visibility file (MS).
            caltable: Name of the input calibration table.
            infile: Antenna positions file obtained with getantposalma task.
            antenna: Filter data selection based on antenna/baseline.
            parameter: List of calibration values; For this purpose, the offsets for all specified antennas.
        """
        infile = ''
        if self.hm_antpos == 'online':
            infile = self.online_antpos_filename

        # Get the antenna and offset lists.
        if self.hm_antpos == 'file':
            filename = os.path.join(self.output_dir, self.antposfile)
            antenna, offsets = self._read_antpos_csvfile(filename, os.path.basename(self.vis))
        else:
            antenna = self.antenna
            offsets = self.offsets

        return {'vis': self.vis, 'caltable': self.caltable, 'infile': infile, 'antenna': antenna, 'parameter': offsets}

    def to_antpos_args(self) -> dict[str, str | bool | list[str] | Literal['both_latest', 'both_closest'] | None]:
        """
        Configure getantposalma task arguments and return them in dictionary format.

        Returns:
            outfile: Name of file to write antenna positions retrieved from DB.
            overwrite: Tells `getantposalma` whether to overwrite the file if it exists. If False and the file exists,
                it will throw an error.
            asdm: The execution block ID (ASDM) of the dataset.
            snr: A float value describing the signal-to-noise threshold. Antennas with snr below the threshold will 
                not be retrieved.
            search: Search algorithm to use. Supports 'both_latest' and 'both_closest'.
            hosts: Priority-ranked list of hosts to query. Can be customized with ANTPOS_SERVICE_URL environment
                variable, a comma-delimited string ordered by priority.
        """
        hosts = utils.get_valid_url('ANTPOS_SERVICE_URL', ANTPOS_SERVICE_URL)
        return {'outfile': self.online_antpos_filename,
                'overwrite': True,
                'asdm': self.context.observing_run.get_ms(self.vis).execblock_id,
                'snr': self.snr,
                'search': self.search,
                'hosts': hosts}

    @property
    def online_antpos_filename(self) -> str:
        eb_antposfile = f"{self.vis.split('.ms')[0]}.{self.antposfile}"
        return os.path.join(self.output_dir, eb_antposfile)

    def __str__(self):
        return (
            f"AlmaAntposInputs:\n"
            f"\tvis: {self.vis}\n"
            f"\tcaltable: {self.caltable}\n"
            f"\thm_antpos: {self.hm_antpos}\n"
            f"\tantposfile: {self.online_antpos_filename}\n"
            f"\tantenna: {self.antenna}\n"
            f"\toffsets: {self.offsets}\n"
            f"\tthreshold: {self.threshold}\n"
            f"\tsnr: {self.snr}\n"
            f"\tsearch: {self.search}"
        )


@task_registry.set_equivalent_casa_task('hifa_antpos')
class ALMAAntpos(antpos.Antpos):
    Inputs = ALMAAntposInputs

    def prepare(self):
        inputs = self.inputs

        if inputs.hm_antpos == 'online':
            # PIPE-51: retrieve json file for MS to include in the call to gencal
            antpos_args = inputs.to_antpos_args()
            if not os.path.exists(antpos_args['outfile']):
                antpos_job = casa_tasks.getantposalma(**antpos_args)
                try:
                    # PIPE-2868: catch RuntimeError from getantposalma task and continue with the current session.
                    self._executor.execute(antpos_job)
                except RuntimeError as ex:
                    LOG.warning('CASA/getantposalma task failed without generating %s: %s', antpos_args['outfile'], ex)
                    traceback_msg = traceback.format_exc()
                    if os.getenv('ALLOW_GETANTPOSALMA_FAILURE', 'false').lower() == 'true':
                        LOG.info(traceback_msg)
                    else:
                        raise exceptions.PipelineException(traceback_msg)
            else:
                LOG.warning('Antenna position file %s exists. Skipping getantposalma task.', antpos_args['outfile'])

            if os.path.exists(antpos_args['outfile']):
                # PIPE-2653 remove antennas from JSON file that are missing from the MS
                self._remove_missing_antennas_from_json(antpos_args['outfile'])
            else:
                # PIPE-2868: likely getantposalma failed and no json file was created.
                # set result offsets to None instead of empty list [] and continue with the current session.
                return AntposResults(offsets=None)

        return super().prepare()

    def _remove_missing_antennas_from_json(self, antposfile: str) -> None:
        """Removes antennas from JSON file that are missing from the measurement set.

        Handles inconsistencies between antennas in the MS and JSON file, which can occur
        due to online database issues or truncated datasets.

        Args:
            antposfile: Path to the antenna position JSON file to modify.
        """
        # get sorted antenna names from measurement set
        ant_names_from_ms = sorted([antenna.name for antenna in self.inputs.ms.antennas])

        try:
            with open(antposfile, 'r', encoding='utf-8') as f:
                query_dict = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            LOG.error('Failed to read JSON file %s: %s', antposfile, e)
            return

        if 'data' not in query_dict:
            LOG.error("The antpos JSON file %s missing required 'data' key.", antposfile)
            return

        # find antennas to remove (in JSON but not in MS)
        ants_from_json = set(query_dict['data'].keys())
        ants_from_ms = set(ant_names_from_ms)

        # PIPE-2652: issue warnings if some antennas from MS are missing in JSON.
        ants_not_in_json = sorted(ants_from_ms - ants_from_json)
        if ants_not_in_json:
            LOG.warning(
                'Antenna(s) from %s are not found in the corresponding antpos JSON file %s : %s',
                self.inputs.vis,
                antposfile,
                utils.commafy(ants_not_in_json, quotes=False),
            )

        # Remove missing antennas and update file
        remove_ants = sorted(ants_from_json - ants_from_ms)
        for ant in remove_ants:
            query_dict['data'].pop(ant)

        if remove_ants:
            LOG.warning(
                'Removed antenna(s) that are missing in %s from the corresponding antpos JSON file %s : %s',
                self.inputs.vis,
                antposfile,
                utils.commafy(remove_ants, quotes=False),
            )
            os.rename(antposfile, antposfile + '.original')
            with open(antposfile, 'w', encoding='utf-8') as f:
                json.dump(query_dict, f, separators=(', ', ': '))

    def analyse(self, result):
        result = super().analyse(result)

        # add the offsets to the result for online query
        antpos_args = self.inputs.to_antpos_args()
        if self.inputs.hm_antpos == 'online' and os.path.exists(antpos_args['outfile']):
            offsets_dict = self._get_antenna_offsets()
            antenna_names, offsets = self._get_antennas_with_significant_offset(offsets_dict)
            if antenna_names:
                result.antenna = ','.join(antenna_names)
                result.offsets = offsets
                LOG.info('Antennas with non-zero corrections applied: %s', result.antenna)

        return result

    def _get_antenna_offsets(self) -> dict[np.str_, np.ndarray[float]]:
        """Retrieves the antenna names and positions from the vis ANTENNA table and computes the offsets.

        Returns:
            Dictionary mapping antenna names to (x, y, z) offset tuples.
        """
        with casa_tools.TableReader(self.inputs.vis + '/ANTENNA') as tb:
            antennas = tb.getcol('NAME')
            # Retrieve antenna positions from the ANTENNA table
            # For ALMA, this is in meters / ITRF.
            tb_positions = tb.getcol('POSITION')

        tb_antpos_dict = dict(zip(antennas, tb_positions.T))

        # Retrieve antenna corrections from antennapos.json
        with open(self.inputs.online_antpos_filename, 'r') as f:
            query_dict = json.load(f)
            db_antpos_dict = query_dict['data']

        # calculate offsets
        offsets_dict = {}
        for antenna in antennas:
            if str(antenna) in db_antpos_dict:
                offsets_dict[antenna] = db_antpos_dict[antenna] - tb_antpos_dict[antenna]

        return offsets_dict

    def _get_antennas_with_significant_offset(
            self,
            offsets_dict: dict[np.str_, np.ndarray[float]],
            ) -> tuple[list[np.str_], list[np.float64]]:
        """
        Identifies antennas with significant non-zero coordinate offsets.

        Args:
            offsets_dict: Dictionary mapping antenna names to (x, y, z) offset tuples.

        Returns:
            A list of antenna names with significant offsets, and a flattened list of their 
            corresponding offset values.
        """
        names = []
        flattened_offsets = []

        for antenna, offsets in offsets_dict.items():
            if np.any(np.abs(offsets) > 0):
                names.append(antenna)
                flattened_offsets.extend(offsets)

        return names, flattened_offsets
