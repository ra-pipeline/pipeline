import os
from typing import Optional

import numpy

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
import pipeline.infrastructure.sessionutils as sessionutils
from pipeline.domain.datatable import DataTableImpl as DataTable
from pipeline.domain import DataType
from pipeline.h.tasks.applycal.applycal import Applycal, ApplycalInputs, ApplycalResults
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry

LOG = infrastructure.get_logger(__name__)


class SDApplycalInputs(ApplycalInputs):
    """
    ApplycalInputs defines the inputs for the Applycal pipeline task.
    """
    flagdetailedsum = vdp.VisDependentProperty(default=True)
    intent = vdp.VisDependentProperty(default='TARGET')

    def __init__(self, context, output_dir=None, vis=None, field=None, spw=None, antenna=None, intent=None, parang=None,
                 applymode=None, flagbackup=None, flagsum=None, flagdetailedsum=None):
        super(SDApplycalInputs, self).__init__(context, output_dir=output_dir, vis=vis, field=field, spw=spw,
                                               antenna=antenna, intent=intent, parang=parang, applymode=applymode,
                                               flagbackup=flagbackup, flagsum=flagsum, flagdetailedsum=flagdetailedsum)


class SDApplycalResults(ApplycalResults):
    def __init__(self, applied=None, data_type: Optional[DataType]=None):
        super(SDApplycalResults, self).__init__(applied, data_type=data_type)


#@task_registry.set_equivalent_casa_task('hsd_applycal')
#@task_registry.set_casa_commands_comment('Calibrations are applied to the data. Final flagging summaries are computed')
class SDApplycal(Applycal):
    """
    Applycal executes CASA applycal tasks for the current context state,
    applying calibrations registered with the pipeline context to the target
    measurement set.

    Applying the results from this task to the context marks the referred
    tables as applied. As a result, they will not be included in future
    on-the-fly calibration arguments.
    """
    Inputs = SDApplycalInputs

    def modify_task_args(self, task_args):
        # override template fn in Applycal with our SD-specific antenna
        # selection arguments
        task_args['antenna'] = '*&&&'
        return task_args

    def _get_flagsum_arg(self, args):
        # CAS-8813 flag fraction should be based on target instead of total
        task_args = super(SDApplycal, self)._get_flagsum_arg(args)
        task_args['intent'] = 'OBSERVE_TARGET#ON_SOURCE'
        return task_args

    def _tweak_flagkwargs(self, template):
        # CAS-8813 flag fraction should be based on target instead of total
        # use of ' rather than " is required to prevent escaping of flagcmds
        return [row + " intent='OBSERVE_TARGET#ON_SOURCE'" for row in template]

    def prepare(self):
        # execute Applycal
        results = super(SDApplycal, self).prepare()

        # Update Tsys in datatable
        context = self.inputs.context
        # this task uses _handle_multiple_vis framework
        msobj = self.inputs.ms
        origin_basename = os.path.basename(msobj.origin_ms)
        datatable_name = os.path.join(context.observing_run.ms_datatable_name, origin_basename)
        datatable = DataTable()
        datatable.importdata(name=datatable_name, readonly=False)
        datatable._update_flag(msobj.name)
        for calapp in results.applied:
            filename = os.path.join(context.output_dir, calapp.vis)
            fieldids = [fieldobj.id for fieldobj in msobj.get_fields(calapp.field)]
            for _calfrom in calapp.calfrom:
                if _calfrom.caltype == 'tsys':
                    LOG.info('Updating Tsys for {0}'.format(os.path.join(calapp.vis)))
                    tsystable = _calfrom.gaintable
                    spwmap = _calfrom.spwmap
                    gainfield = _calfrom.gainfield
                    datatable._update_tsys(context, filename, tsystable, spwmap, fieldids, gainfield)

        # here, full export is necessary
        datatable.exportdata(minimal=False)

        sdresults = SDApplycalResults(applied=results.applied, data_type=self.applied_data_type)
        sdresults.summaries = results.summaries
        if hasattr(results, 'flagsummary'):
            sdresults.flagsummary = results.flagsummary

        # set unit according to applied calibration
        set_unit(msobj, results.applied)

        return sdresults


def set_unit(ms, calapp):
    target_fields = ms.get_fields(intent='TARGET')
    data_units = dict((f.id, '') for f in target_fields)
    for a in calapp:
        calto = a.calto
        field_name = calto.field
        if len(field_name) == 0:
            field = ms.get_fields(intent='TARGET')
        else:
            field = [f for f in ms.get_fields(name=field_name) if 'TARGET' in f.intents]
        if len(field) == 0:
            continue

        assert len(field) == 1
        field_id = field[0].id
        caltypes = [cf.caltype for cf in a.calfrom]
        if ('ps' in caltypes) and ('tsys' in caltypes):
            data_units[field_id] = 'K'
        else:
            LOG.warning('Calibration of {} (field {}) is not correct. Missing pscal and/or tsyscal.'.format(ms.basename, field_name))
        if 'amp' in caltypes or 'gaincal' in caltypes:
            if data_units[field_id] == 'K':
                data_units[field_id] = 'Jy'

    unit_list = numpy.asarray(list(data_units.values()))
    if numpy.all(unit_list == 'K'):
        data_unit = 'K'
    elif numpy.all(unit_list == 'Jy'):
        data_unit = 'Jy'
    elif numpy.any(unit_list == 'Jy'):
        LOG.warning(
            'Calibration of {} is not correct. Some of calibrations (pscal, tsyscal, ampcal) are missing.'.fomrat(ms.basename))
        data_unit = ''
    else:
        data_unit = ''

    if data_unit != '':
        with casa_tools.TableReader(ms.name, nomodify=False) as tb:
            colnames = tb.colnames()
            target_columns = set(colnames) & set(['DATA', 'FLOAT_DATA', 'CORRECTED_DATA'])
            for col in target_columns:
                tb.putcolkeyword(col, 'UNIT', data_unit)


# Tier-0 parallelization
class HpcSDApplycalInputs(SDApplycalInputs):
    # use common implementation for parallel inputs argument
    parallel = sessionutils.parallel_inputs_impl()

    def __init__(self, context, output_dir=None, vis=None, field=None, spw=None, antenna=None, intent=None, parang=None,
                 applymode=None, flagbackup=None, flagsum=None, flagdetailedsum=None, parallel=None):
        super(HpcSDApplycalInputs, self).__init__(context, output_dir=output_dir, vis=vis, field=field, spw=spw,
                                               antenna=antenna, intent=intent, parang=parang, applymode=applymode,
                                               flagbackup=flagbackup, flagsum=flagsum, flagdetailedsum=flagdetailedsum)
        self.parallel = parallel


@task_registry.set_equivalent_casa_task('hsd_applycal')
@task_registry.set_casa_commands_comment('Calibrations are applied to the data. Final flagging summaries are computed')
class HpcSDApplycal(sessionutils.ParallelTemplate):
    Inputs = HpcSDApplycalInputs
    Task = SDApplycal

    @basetask.result_finaliser
    def get_result_for_exception(self, vis, exception):
        LOG.error('Error operating apply calibration for {!s}'.format(os.path.basename(vis)))
        LOG.error('{0}({1})'.format(exception.__class__.__name__, str(exception)))
        import traceback
        tb = traceback.format_exc()
        if tb.startswith('None'):
            tb = '{0}({1})'.format(exception.__class__.__name__, str(exception))
        return basetask.FailedTaskResults(self.__class__, exception, tb)
