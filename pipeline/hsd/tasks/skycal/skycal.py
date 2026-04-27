"""The skycal task module to calibrate sky background."""
from __future__ import annotations

import collections
import copy
import os
from typing import TYPE_CHECKING

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.sessionutils as sessionutils
from pipeline.infrastructure.utils import relative_path
import pipeline.infrastructure.vdp as vdp
from pipeline.h.heuristics import caltable as caltable_heuristic
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry
from pipeline.domain.datatable import OnlineFlagIndex
from ..common import SingleDishResults

if TYPE_CHECKING:
    from numpy import generic
    from numpy.typing import NDArray

    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.get_logger(__name__)

# Threshold of the elevation difference of QA score
ELEVATION_DIFFERENCE_THRESHOLD = 3.0  # deg


class SDSkyCalInputs(vdp.StandardInputs):
    """Inputs class for SDSkyCal task."""
    parallel = sessionutils.parallel_inputs_impl()

    calmode = vdp.VisDependentProperty(default='auto')
    elongated = vdp.VisDependentProperty(default=False)
    field = vdp.VisDependentProperty(default='')
    fraction = vdp.VisDependentProperty(default='10%')
    noff = vdp.VisDependentProperty(default=-1)
    outfile = vdp.VisDependentProperty(default='')
    scan = vdp.VisDependentProperty(default='')
    spw = vdp.VisDependentProperty(default='')
    width = vdp.VisDependentProperty(default=0.5)

    @vdp.VisDependentProperty
    def infiles(self) -> str:
        """Return name of MS. Alias for "vis" attribute."""
        return self.vis

    @infiles.convert
    def infiles(self, value: str | list[str]) -> str | list[str]:
        """Convert value into expected type.

        Currently, no conversion is performed.

        Args:
            value: Name of MS, or the list of names.

        Returns:
            Converted value. Currently return input value as is.
        """
        self.vis = value
        return value

    # docstring and type hints: supplements hsd_skycal
    def __init__(
            self,
            context: Context,
            calmode: str | None = None,
            fraction: float | None = None,
            noff: int | None = None,
            width: float | None = None,
            elongated: bool | None = None,
            output_dir: str | None = None,
            infiles: str | None = None,
            outfile: str | None = None,
            field: str | None = None,
            spw: str | None = None,
            scan: str | None = None,
            parallel: bool | str | None = None
            ):
        """Initialize SDK2JyCalInputs instance.

        Args:
            context: Pipeline context object containing state information.

            calmode: Calibration mode.
                Available options are 'auto' (default), 'ps', 'otf', and
                'otfraster'. When 'auto' is set, the task will use preset
                calibration mode that is determined by inspecting data.
                'ps' mode is simple position switching using explicit reference
                scans. Other two modes, 'otf' and 'otfraster', will generate
                reference data from scans at the edge of the map. Those modes
                are intended for OTF observation and the former is defined for
                generic scanning pattern such as Lissajous, while the latter is
                specific use for raster scan.

                Options: ``'auto'``, ``'ps'``, ``'otf'``, ``'otfraster'``

                Default: ``None`` (equivalent to ``'auto'``)

            fraction: Sub-parameter for calmode. Edge marking parameter for
                'otf' and 'otfraster' mode. It specifies a number of OFF scans
                as a fraction of total number of data points.

                Options: String style like '20%', or float value less than 1.0.
                    For 'otfraster' mode, you can also specify 'auto'.

                Default: ``None`` (equivalent to ``'10%'``)

            noff: Sub-parameter for calmode. Edge marking parameter for
                'otfraster' mode. It is used to specify a number of OFF scans
                near edge directly instead to specify it by fractional
                number by 'fraction'. If it is set, the value will come
                before setting by 'fraction'.

                Options: any positive integer value

                Default: ``None`` (equivalent to ``''``)

            width: Sub-parameter for calmode. Edge marking parameter for
                'otf' mode. It specifies pixel width with respect to
                a median spatial separation between neighboring two data
                in time. Default will be fine in most cases.

                Options: any float value

                Default: ``None`` (equivalent to ``0.5``)

            elongated: Sub-parameter for calmode. Edge marking parameter
                for 'otf' mode. Please set True only if observed area is
                elongated in one direction.

                Default: ``None`` (equivalent to ``False``)

            output_dir: Name of output directory.

            infiles: List of data files. These must be a name of
                MeasurementSets that are registered to context
                via hsd_importdata or hsd_restoredata task.

                Example: ``vis=['X227.ms', 'X228.ms']``

            outfile: Name of the output file.

            field: Data selection by field name.

            spw: Data selection by spw.

                Example: ``'3,4'`` (generate caltable for spw 3 and 4), ``['0','2']`` (spw 0 for first data, 2 for second)

                Default: ``None`` (process all science spws)

            scan: Data selection by scan number. (default all scans)

                Example: ``'22,23'`` (use scan 22 and 23 for calibration), ``['22','24']`` (scan 22 for first data, 24 for second)

                Default: None (process all scans)

            parallel: Execute using CASA HPC functionality, if available.

                Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

                Default: ``None`` (equivalent to ``'automatic'``)
        """
        super().__init__()

        # context and vis must be set first so that properties that require
        # domain objects can be function
        self.context = context
        self.infiles = infiles
        self.output_dir = output_dir
        self.outfile = outfile

        self.calmode = calmode
        self.fraction = fraction
        self.noff = noff
        self.width = width
        self.elongated = elongated

        self.field = field
        self.spw = spw
        self.scan = scan

        self.parallel = parallel

    def to_casa_args(self) -> dict:
        """Convert Inputs instance to the list of keyword arguments for sdcal.

        Returns:
            Keyword arguments for sdcal.
        """
        args = super().to_casa_args()

        # overwrite is always True
        args['overwrite'] = True

        # parameter name for input data is 'infile'
        args['infile'] = args.pop('infiles')

        # vis and parallel are not necessary
        del args['vis']
        del args['parallel']

        return args


class SDSkyCalResults(SingleDishResults):
    """Class to hold processing result of SDSkyCal task."""

    def __init__(
            self,
            task: str | None = None,
            success: bool | None = None,
            outcome: str | None = None
            ) -> None:
        """Initialize SDSkyCalResults instance.

        Args:
            task: Name of task.
            success: A boolean to indicate if the task execution was successful
            (True) or not (False).
            outcome: Outcome of the task.
        """
        super().__init__(task, success, outcome)
        self.final = self.outcome

    def merge_with_context(self, context: Context) -> None:
        """Merge result instance into context.

        The CalApplication instance updated by the skycal task is added to
        the pipeline context.

        Args:
            context: Pipeline context object containing state information.
        """
        super().merge_with_context(context)

        if self.outcome is None:
            return

        for calapp in self.outcome:
            context.callibrary.add(calapp.calto, calapp.calfrom)

    def _outcome_name(self) -> str:
        """Return string representing the outcome.

        Returns:
            string of outcome.
        """
        return str(self.outcome)


class SerialSDSkyCal(basetask.StandardTaskTemplate):
    """Generate sky calibration table."""

    Inputs = SDSkyCalInputs

    def prepare(self) -> SDSkyCalResults:
        """Prepare arguments for CASA job and execute it.

        Returns:
           SDSkyCalResults object.
        """
        args = self.inputs.to_casa_args()
        LOG.trace('args: {}'.format(args))

        # retrieve ms domain object
        ms = self.inputs.ms
        calibration_strategy = ms.calibration_strategy
        default_field_strategy = calibration_strategy['field_strategy']

        # take calmode from calibration strategy if it is set to 'auto'
        if args['calmode'] is None or args['calmode'].lower() == 'auto':
            args['calmode'] = calibration_strategy['calmode']

        assert args['calmode'] in ['ps', 'otfraster', 'otf']

        # spw selection ---> task.prepare
        if args['spw'] is None or len(args['spw']) == 0:
            spw_list = ms.get_spectral_windows(science_windows_only=True)
            args['spw'] = ','.join(map(str, [spw.id for spw in spw_list]))

        # field selection ---> task.prepare
        if args['field'] is None or len(args['field']) == 0:
            field_strategy = default_field_strategy
        else:
            field_strategy = {}
            field_ids = casa_tools.ms.msseltoindex(vis=ms.name, field=args['field'])
            for field_id in field_ids:
                for target_id, reference_id in default_field_strategy.items():
                    if field_id == target_id:
                        field_strategy[field_id] = default_field_strategy[field_id]
                        continue
                    elif field_id == reference_id:
                        field_strategy[target_id] = field_id
                        continue

        # scan selection
        if args['scan'] is None:
            args['scan'] = ''

        # intent
        if args['calmode'] in ['otf', 'otfraster']:
            args['intent'] = 'OBSERVE_TARGET#ON_SOURCE'

        calapps = []
        for target_id, reference_id in field_strategy.items():
            myargs = copy.deepcopy(args)

            # output file
            reference_field_name = ms.get_fields(reference_id)[0].clean_name
            if myargs['outfile'] is None or len(myargs['outfile']) == 0:
                namer = caltable_heuristic.SDSkyCaltable()
                # filenamer requires field name instead of id
                myargs['field'] = reference_field_name
                try:
                    # we temporarily need 'vis'
                    myargs['vis'] = myargs['infile']
                    myargs['outfile'] = relative_path(namer.calculate(output_dir=self.inputs.output_dir,
                                                                      stage=self.inputs.context.stage,
                                                                      **myargs))
                finally:
                    del myargs['vis']
            else:
                myargs['outfile'] = myargs['outfile'] + '.{}'.format(reference_field_name)

            # field
            myargs['field'] = str(reference_id)

            LOG.debug('args for sdcal: {}'.format(myargs))

            # create job
            job = casa_tasks.sdcal(**myargs)

            # execute job
            LOG.debug('Table cache before sdcal: {}'.format(casa_tools.table.showcache()))
            try:
                self._executor.execute(job)
            finally:
                LOG.debug('Table cache after sdcal: {}'.format(casa_tools.table.showcache()))

            # check if caltable is empty
            with casa_tools.TableReader(myargs['outfile']) as tb:
                is_caltable_empty = tb.nrows() == 0
            if is_caltable_empty:
                continue

            # make a note of the current inputs state before we start fiddling
            # with it. This origin will be attached to the final CalApplication.
            origin = callibrary.CalAppOrigin(task=SerialSDSkyCal,
                                             inputs=args)

            calto = callibrary.CalTo(vis=myargs['infile'],
                                     spw=myargs['spw'],
                                     field=str(target_id),
                                     intent='TARGET')

            # create SDCalFrom object
            calfrom = callibrary.CalFrom(gaintable=myargs['outfile'],
                                         gainfield=str(reference_id),
                                         interp='linear,linear',
                                         caltype=myargs['calmode'])

            # create CalApplication object
            calapp = callibrary.CalApplication(calto, calfrom, origin)
            calapps.append(calapp)

        results = SDSkyCalResults(task=self.__class__,
                                  success=True,
                                  outcome=calapps)
        return results

    def analyse(self, result: SDSkyCalResults) -> SDSkyCalResults:
        """Analyse SDSkyCalResults instance produced by prepare.

        Args:
            result: SDSkyCalResults instance.

        Returns:
            Updated SDSkyCalResults instance.
        """
        return result


@task_registry.set_equivalent_casa_task('hsd_skycal')
@task_registry.set_casa_commands_comment('Generates sky calibration table according to calibration strategy.')
class SDSkyCal(sessionutils.ParallelTemplate):
    """Class to generate sky calibration table."""

    Inputs = SDSkyCalInputs
    Task = SerialSDSkyCal


def get_elevation(
        datatable_name: str,
        spw_id: int | str,
        antenna_id: int | str,
        field_id: int | str,
        on_source: bool
) -> dict[str, NDArray[generic]]:
    """Get elevation and associated time and flag from datatable.

    Args:
        datatable_name: Name of the datatable.
        spw_id: Spectral window ID.
        antenna_id: Antenna ID.
        field_id: Field ID.
        on_source: If True, get elevation for on-source data,
            otherwise for off-source data.

    Returns:
        Dictionary with time and elevation.
        - time: Array of time in seconds.
        - el: Array of elevation in radians.
        - online_flag: Array of online flags
            (False for valid, True for invalid data).
    """
    ro_datatable_name = os.path.join(datatable_name, 'RO')
    rw_datatable_name = os.path.join(datatable_name, 'RW')
    with casa_tools.TableReader(ro_datatable_name) as tb:
        taql = f'IF=={spw_id}&&ANTENNA=={antenna_id}&&FIELD_ID=={field_id}'
        if on_source:
            taql += '&&SRCTYPE==0'
        else:
            taql += '&&SRCTYPE!=0'
        selected = tb.query(taql)
        if selected.nrows() == 0:
            selected.close()
            return {
                'time': np.array([], dtype=float),
                'el': np.array([], dtype=float),
                'online_flag': np.array([], dtype=bool)
            }
        npol = selected.getcell('NPOL', 0)
        time = selected.getcol('TIME')
        el = selected.getcol('EL')
        rows = selected.rownumbers()
        selected.close()

    with casa_tools.TableReader(rw_datatable_name) as tb:
        it = (
            np.all(tb.getcellslice(
                'FLAG_PERMANENT',
                i,
                blc=[0, OnlineFlagIndex],
                trc=[npol - 1, OnlineFlagIndex],
                incr=[1, 1]
            ) != 1) for i in rows
        )
        online_flag = np.fromiter(it, dtype=bool)

    return {'time': time, 'el': el, 'online_flag': online_flag}


def compute_elevation_difference(context: Context, results: SDSkyCalResults) -> dict:
    """Compute elevation difference.

    Args:
        context: Pipeline context object containing state information.
        results: SDSkyCalResults instance.

    Returns:
        dictionary[field_id][antenna_id][spw_id]
            Value of the dictionary should be ElevationDifference and the value should
            contain the result from one MS (given that SDSkyCal is per-MS task).
    """
    ElevationDifference = collections.namedtuple('ElevationDifference',
                                                 ['timeon', 'elon', 'flagon',
                                                  'timecal', 'elcal',
                                                  'time0', 'eldiff0',
                                                  'time1', 'eldiff1'])

    if not isinstance(results, SDSkyCalResults):
        raise TypeError('Results type should be SDSkyCalResults')

    calapps = results.outcome

    resultdict = {}

    for calapp in calapps:
        calto = calapp.calto
        vis = calto.vis
        ms = context.observing_run.get_ms(vis)
        target_field = calto.field
        if target_field.isdigit():
            field_id_on = int(target_field)
        else:
            fields = ms.get_fields(name=target_field)
            assert len(fields) > 0
            field_id_on = fields[0].id

        antenna_ids = [ant.id for ant in ms.antennas]

        science_spw = ms.get_spectral_windows(science_windows_only=True)

        calfroms = calapp.calfrom

        for calfrom in calfroms:
            caltable = calfrom.gaintable

            # FIELD_ID
            gainfield = calfrom.gainfield
            if gainfield.isdigit():
                field_id_off = int(gainfield)
            else:
                fields = ms.get_fields(name=gainfield)
                assert len(fields) > 0
                field_id_off = fields[0].id
            LOG.info('Computing elevation difference for "{}" Field ID {} (ON) and {} (OFF)'
                     ''.format(ms.basename, field_id_on, field_id_off))

            resultfield = {}

            for antenna_id in antenna_ids:

                resultant = {}

                for spw in science_spw:
                    spw_id = spw.id

                    # get timestamp from caltable
                    with casa_tools.TableReader(caltable) as tb:
                        selected = tb.query('SPECTRAL_WINDOW_ID=={}&&ANTENNA1=={}'.format(spw_id, antenna_id))
                        timecal = selected.getcol('TIME') / 86400.0  # sec -> day
                        selected.close()

                    # access DataTable to get elevation
                    datatable_name = os.path.join(
                        context.observing_run.ms_datatable_name,
                        os.path.basename(ms.origin_ms)
                    )
                    data_on = get_elevation(
                        datatable_name,
                        spw_id, antenna_id, field_id_on, on_source=True
                    )
                    timeon = data_on['time']
                    elon = data_on['el']
                    flagon = data_on['online_flag']
                    data_off = get_elevation(
                        datatable_name,
                        spw_id, antenna_id, field_id_off, on_source=False
                    )
                    timeoff = data_off['time']
                    eloff = data_off['el']
                    flagoff = data_off['online_flag']
                    eloff_valid = eloff[np.logical_not(flagoff)]
                    timeoff_valid = timeoff[np.logical_not(flagoff)]
                    elcal = eloff_valid[
                        [np.argmin(np.abs(timeoff_valid - t)) for t in timecal]
                    ]

                    eldiff0 = []
                    eldiff1 = []
                    time0 = []
                    time1 = []
                    for t, el, flg in zip(timeon, elon, flagon):
                        # do not process flagged data
                        if flg:
                            continue

                        dt = timecal - t
                        idx0 = np.where(dt < 0)[0]
                        if len(idx0) > 0:
                            i = np.argmax(timecal[idx0])
                            time0.append(t)
                            eldiff0.append(el - elcal[idx0[i]])
                        idx1 = np.where(dt >= 0)[0]
                        if len(idx1) > 0:
                            i = np.argmin(timecal[idx1])
                            time1.append(t)
                            eldiff1.append(el - elcal[idx1[i]])
                    eldiff0 = np.asarray(eldiff0)
                    eldiff1 = np.asarray(eldiff1)
                    time0 = np.asarray(time0)
                    time1 = np.asarray(time1)

                    result = ElevationDifference(timeon=timeon, elon=elon,
                                                 flagon=flagon,
                                                 timecal=timecal, elcal=elcal,
                                                 time0=time0, eldiff0=eldiff0,
                                                 time1=time1, eldiff1=eldiff1)

                    resultant[spw_id] = result

                resultfield[antenna_id] = resultant

            resultdict[field_id_on] = resultfield

    return resultdict
