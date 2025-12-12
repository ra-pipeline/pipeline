import collections
from operator import attrgetter, itemgetter

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import MeasurementSet
from pipeline.h.heuristics import caltable as caltable_heuristic
from pipeline.h.heuristics.tsysfieldmap import get_intent_to_tsysfield_map
from pipeline.h.heuristics.tsysspwmap import tsysspwmap
from pipeline.infrastructure import casa_tasks, casa_tools, task_registry

from . import resultobjects

__all__ = [
    'SerialTsyscal',
    'Tsyscal',
    'TsyscalInputs',
]

LOG = infrastructure.get_logger(__name__)


class TsyscalInputs(vdp.StandardInputs):
    """
    TsyscalInputs defines the inputs for the Tsyscal pipeline task.
    """
    chantol = vdp.VisDependentProperty(default=1)

    @vdp.VisDependentProperty
    def caltable(self):
        """
        Get the caltable argument for these inputs.

        If set to a table-naming heuristic, this should give a sensible name
        considering the current CASA task arguments.
        """
        namer = caltable_heuristic.TsysCaltable()
        casa_args = self._get_task_args(ignore=('caltable',))
        return namer.calculate(output_dir=self.output_dir, stage=self.context.stage, **casa_args)

    parallel = sessionutils.parallel_inputs_impl(default=False)

    # docstring and type hints: supplements h_tsyscal
    def __init__(self, context, output_dir=None, vis=None, caltable=None, chantol=None, parallel=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: List of input visibility files.

                Example: ``vis=['ngc5921.ms']``

            caltable: Name of output gain calibration tables.

                Example: ``caltable='ngc5921.gcal'``

            chantol: The tolerance in channels for mapping atmospheric calibration windows (TDM) to science windows (FDM or TDM).

                Example: ``chantol=5``

            parallel: Process multiple MeasurementSets in parallel using the casampi parallelization framework.

                Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

                Default: ``None`` (equivalent to ``False``)

        """
        super().__init__()

        # pipeline inputs
        self.context = context
        # vis must be set first, as other properties may depend on it
        self.vis = vis
        self.output_dir = output_dir

        # data selection arguments
        self.caltable = caltable

        # solution parameters
        self.chantol = chantol
        self.parallel = parallel

    # Convert to CASA gencal task arguments.
    def to_casa_args(self):
        return {
            'vis': self.vis,
            'caltable': self.caltable
        }


class SerialTsyscal(basetask.StandardTaskTemplate):
    Inputs = TsyscalInputs

    def prepare(self) -> resultobjects.TsyscalResults:
        inputs = self.inputs

        # make a note of the current inputs state before we start fiddling
        # with it. This origin will be attached to the final CalApplication.
        origin = callibrary.CalAppOrigin(task=Tsyscal, inputs=inputs.to_casa_args())

        # construct the Tsys cal file
        gencal_args = inputs.to_casa_args()
        gencal_job = casa_tasks.gencal(caltype='tsys', **gencal_args)
        self._executor.execute(gencal_job)

        tsys_table = gencal_args['caltable']

        LOG.todo('tsysspwmap heuristic re-reads measurement set!')
        LOG.todo('tsysspwmap heuristic won\'t handle missing file')
        nospwmap, spwmap = tsysspwmap(ms=inputs.ms, tsystable=tsys_table, channel_tolerance=inputs.chantol)

        calfrom_defaults = dict(caltype='tsys', spwmap=spwmap, interp='linear,linear')

        is_single_dish = utils.contains_single_dish(inputs.context)
        calapps = get_calapplications(inputs.ms, tsys_table, calfrom_defaults, origin, spwmap, is_single_dish)

        return resultobjects.TsyscalResults(pool=calapps, unmappedspws=nospwmap)

    def analyse(self, result: resultobjects.TsyscalResults) -> resultobjects.TsyscalResults:
        # double-check that the caltable was actually generated
        on_disk = [ca for ca in result.pool if ca.exists()]
        result.final[:] = on_disk

        missing = [ca for ca in result.pool if ca not in on_disk]
        result.error.clear()
        result.error.update(missing)

        return result


@task_registry.set_equivalent_casa_task('h_tsyscal')
@task_registry.set_casa_commands_comment('The Tsys calibration and spectral window map is computed.')
class Tsyscal(sessionutils.ParallelTemplate):
    Inputs = TsyscalInputs
    Task = SerialTsyscal


def get_calapplications(ms: MeasurementSet, tsys_table: str, calfrom_defaults: dict, origin: callibrary.CalAppOrigin,
                        spw_map: list, is_single_dish: bool) -> list[callibrary.CalApplication]:
    """
    Get a list of CalApplications that apply a Tsys caltable to a measurement
    set using the gainfield mapping defined in CAS-12213.

    Note: this function only provides the gainfield argument for the CalFrom
    constructor. Any other required CalFrom constructor arguments should be
    provided to this function via the calfrom_defaults parameter.

    Args:
        ms: MeasurementSet to apply calibrations to.
        tsys_table: name of Tsys table.
        calfrom_defaults: dict of CalFrom constructor arguments.
        origin: CalOrigin for the created CalApplications.
        spw_map: Tsys SpW map.
        is_single_dish: boolean declaring if current MS is for Single-Dish.

    Returns:
        List of CalApplications.
    """
    # Get the map of intent:gainfield
    soln_map = get_intent_to_tsysfield_map(ms, is_single_dish)

    # Create the static dict of calfrom arguments. Only the 'gainfield' argument changes from calapp to calapp; the
    # other arguments remain unchanged.
    calfrom_args = dict(calfrom_defaults)
    calfrom_args['gaintable'] = tsys_table

    # get the mapping of field ID to unambiguous identifier for more user friendly logs
    field_id_to_identifier = utils.get_field_identifiers(ms)

    # create a domain object mapping of science spw to Tsys spw
    domain_spw_map = {ms.spectral_windows[i]: ms.spectral_windows[j] for i, j in enumerate(spw_map)}

    # Now loop through the MS intents, creating a specific Tsys registration for each intent.
    calapps = []
    for intent in ms.intents:
        # get the preferred Tsys gainfield for this intent, falling back to 'nearest' if not specified
        gainfield = soln_map.get(intent, 'nearest')

        # The CASA callibrary cannot handle registrations with multiple fldmap fields, e.g., fldmap='1,2'.
        if ',' in gainfield:
            LOG.info('Calculating workaround for CASA callibrary fldmap incompatibility: '
                     '{} intent -> fldmap={!r}'.format(intent, gainfield))
            # get the fields for this non-Tsys intent
            fields_with_intent = ms.get_fields(intent=intent)
            # get the Tsys fields that were to be applied in the fldmap
            tsys_fields = ms.get_fields(task_arg=gainfield)

            # holds mapping of field,spw -> Tsys field
            field_to_tsys_field = collections.defaultdict(dict)

            # For the fields for the current non-Tsys intent, we'll emulate the
            # CASA gainfield='nearest' option by selecting the spatially
            # closest Tsys field with the same tuning.
            me = casa_tools.measures
            qa = casa_tools.quanta
            for non_tsys_field in fields_with_intent:
                non_tsys_direction = non_tsys_field.mdirection

                # For multi-tuning EBs, the spws may need different gainfield arguments. For example, in
                # uid://A002/Xcf3a9c/X3a3d, the phase cal has no Tsys scans and was observed with three different
                # tunings. Each tuning is distinct and was used for a different target field. Each target field *does*
                # have a Tsys scan. Due to the lack of Tsys scans on the phase cal, the target fields are selected as
                # the fallback gainfields (e.g., # gainfield='A,B,C'), which due to the CASA callibrary
                # limitation we now need to boil down to the closest target that was observed using the same
                # spectral setup.

                # get the spws used to observe with intent XXX for this non-Tsys field
                non_tsys_scans = ms.get_scans(scan_intent=intent, field=non_tsys_field.id)
                non_tsys_spws = {dd.spw for scan in non_tsys_scans for dd in scan.data_descriptions}
                # filter out non-science windows, leaving just the spws for this non-Tsys field
                non_tsys_spws = [spw for spw in non_tsys_spws if spw.type in ('TDM', 'FDM')]

                for non_tsys_spw in sorted(non_tsys_spws, key=attrgetter('id')):
                    # check to see if there's data for the field/intent/spw combination
                    scans = ms.get_scans(scan_intent=intent, spw=non_tsys_spw.id, field=non_tsys_field.id)
                    if not scans:
                        # If there's no data, there's no calibration required.
                        continue

                    # for each spw used for the intent=XXX scan, find the Tsys field that was observed using the Tsys
                    # spw which is mapped to this science spw
                    tsys_spw_for_spw = domain_spw_map[non_tsys_spw]
                    tsys_fields_with_required_spw = [f for f in tsys_fields if tsys_spw_for_spw in f.valid_spws]

                    LOG.debug('Candidate Tsys fields for spw {}: {}'
                              ''.format(non_tsys_spw.id, ','.join(f.name for f in tsys_fields_with_required_spw)))

                    separations = []
                    for tsys_field in tsys_fields_with_required_spw:
                        tsys_direction = tsys_field.mdirection
                        separation = me.separation(tsys_direction, non_tsys_direction)
                        separation_degs = qa.getvalue(qa.convert(separation, 'deg'))[0]
                        separations.append((tsys_field, separation_degs))

                    if not separations:
                        msg = ('Failed Tsys calibration for {} spw {}: no Tsys scan with the same tuning identified'
                               ''.format(non_tsys_field.name, non_tsys_spw.id))
                        LOG.error(msg)
                        continue

                    closest = min(separations, key=itemgetter(1))[0]
                    LOG.info('Tying {} field #{} spw #{} to closest Tsys field {} spw #{}'.format(
                        intent, field_id_to_identifier[non_tsys_field.id], non_tsys_spw.id,
                        field_id_to_identifier[closest.id], tsys_spw_for_spw.id)
                    )
                    field_to_tsys_field[non_tsys_field][non_tsys_spw.id] = closest

            # create a CalTo specifically for the intent fields with their selected Tsys field
            for non_tsys_field, spw_to_tsys_field in field_to_tsys_field.items():
                field_arg = field_id_to_identifier[non_tsys_field.id]
                for spw, tsys_field in spw_to_tsys_field.items():
                    gainfield_arg = field_id_to_identifier[tsys_field.id]
                    calto = callibrary.CalTo(vis=ms.name, intent=intent, spw=spw, field=field_arg)
                    calfrom = callibrary.CalFrom(gainfield=gainfield_arg, **calfrom_args)
                    calapp = callibrary.CalApplication(calto, calfrom, origin)
                    calapps.append(calapp)

        else:
            LOG.info('Setting Tsys gainfield={!r} for {} data in {}'.format(gainfield, intent, ms.basename))

            # With gainfield set appropriately, construct the CalApplication and add it to the results
            calto = callibrary.CalTo(vis=ms.name, intent=intent)
            calfrom = callibrary.CalFrom(gainfield=gainfield, **calfrom_args)
            calapp = callibrary.CalApplication(calto, calfrom, origin)
            calapps.append(calapp)

    return calapps
