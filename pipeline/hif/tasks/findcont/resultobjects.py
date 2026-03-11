import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.conditions as conditions
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.contfilehandler as contfilehandler

import numpy

LOG = infrastructure.get_logger(__name__)


class FindContResult(basetask.Results):
    def __init__(
        self,
        result_cont_ranges,
        cont_ranges,
        joint_mask_names,
        num_found,
        num_total,
        single_range_channel_fractions,
        momDiffSNRs,
        skip_stage=False,
        warning_details=None,
    ):
        super(FindContResult, self).__init__()
        self.result_cont_ranges = result_cont_ranges
        self.cont_ranges = cont_ranges
        self.joint_mask_names = joint_mask_names
        self.num_found = num_found
        self.num_total = num_total
        self.mitigation_error = False
        self.plot_path = None
        self.single_range_channel_fractions = single_range_channel_fractions
        self.momDiffSNRs = momDiffSNRs
        self.skip_stage = skip_stage
        self.warning_details = {} if warning_details is None else warning_details

    def merge_with_context(self, context):
        aggregated_warnings = [
            warning
            for spw_warnings in self.warning_details.values()
            for warnings in spw_warnings.values()
            for warning in warnings
        ]

        if not self.mitigation_error:
            # write the new ranges to the continuum file
            if not self.skip_stage:
                # PIPE-2255: if the findcontinuum heuristics is skipped (e.g. for the VLA cube imaging workflow),
                # we will skip the cont.dat writeout to avoid a blank cont.dat file.
                contfile_handler = contfilehandler.ContFileHandler(context.contfile)
                contfile_handler.write(self.cont_ranges)

            # Store new selection for subsequent mfs or cont imaging step.
            # NOTE: This only works for the default setup, not for a user supplied list.
            # TODO: Catch user supplied list case.
            clean_list_pending = []
            for i, target in enumerate(context.clean_list_pending):
                new_target = target
                target_ok = True
                if target['specmode'] in ('mfs', 'cont'):
                    source_name = utils.dequote(target['field'])
                    spwids = target['spw']
                    new_spwids = []
                    new_spw_sel = 'NEW' in [self.result_cont_ranges[source_name][spwid]['status'] for spwid in spwids.split(',')]

                    all_continuum = True
                    low_bandwidth = True
                    low_spread = True
                    if new_spw_sel:
                        spwsel = {}
                        for spwid in spwids.split(','):
                            if (self.cont_ranges['fields'][source_name][spwid]['ranges'] == ['NONE']) and (target['intent'] == 'TARGET'):
                                spwsel['spw%s' % (spwid)] = ''
                                warning_message = 'No continuum frequency range information found for %s, spw %s.' % (
                                    target['field'],
                                    spwid,
                                )
                                LOG.warning(warning_message)
                                aggregated_warnings.append(
                                    {
                                        'category': 'missing_continuum_range',
                                        'field': target['field'],
                                        'spw': spwid,
                                        'message': warning_message,
                                    }
                                )
                                all_continuum = False
                            elif self.cont_ranges['fields'][source_name][spwid]['ranges'] == ['ALL']:
                                spwsel['spw%s' % (spwid)] = 'ALL'
                            elif self.cont_ranges['fields'][source_name][spwid]['ranges'] == ['ALLCONT']:
                                spwsel['spw%s' % (spwid)] = 'ALLCONT'
                            else:
                                new_spwids.append(spwid)
                                spwsel['spw%s' % (spwid)] = ';'.join(['%.10f~%.10fGHz' % (float(cont_range['range'][0]), float(cont_range['range'][1])) for cont_range in
                                self.cont_ranges['fields'][source_name][spwid]['ranges'] if isinstance(cont_range, dict)])
                                refers = numpy.array([cont_range['refer'] for cont_range in self.cont_ranges['fields'][source_name][spwid]['ranges'] if isinstance(cont_range, dict)])
                                if (refers == 'TOPO').all():
                                    refer = 'TOPO'
                                elif (refers == 'LSRK').all():
                                    refer = 'LSRK'
                                elif (refers == 'SOURCE').all():
                                    refer = 'SOURCE'
                                else:
                                    refer = 'UNDEFINED'
                                spwsel['spw%s' % (spwid)] = '%s %s' % (spwsel['spw%s' % (spwid)], refer)
                                if 'ALL' not in self.cont_ranges['fields'][source_name][spwid]['ranges'] or 'ALLCONT' not in self.cont_ranges['fields'][source_name][spwid]['flags']:
                                    all_continuum = False

                            low_bandwidth = low_bandwidth and 'LOWBANDWIDTH' in self.cont_ranges['fields'][source_name][spwid]['flags']
                            low_spread = low_spread and 'LOWSPREAD' in self.cont_ranges['fields'][source_name][spwid]['flags']

                        new_spwids = ','.join(new_spwids)
                        if (new_spwids == '') and (target['intent'] == 'TARGET'):
                            warning_message = 'No continuum selection for target %s, spw %s. Will not image this selection.' % (
                                new_target['field'],
                                new_target['spw'],
                            )
                            LOG.warning(warning_message)
                            aggregated_warnings.append(
                                {
                                    'category': 'selection_removed',
                                    'field': new_target['field'],
                                    'spw': new_target['spw'],
                                    'message': warning_message,
                                }
                            )
                            target_ok = False
                        else:
                            new_target['spw'] = new_spwids
                            new_target['spwsel_lsrk'] = spwsel
                            new_target['spwsel_all_cont'] = all_continuum
                            new_target['spwsel_low_bandwidth'] = low_bandwidth
                            new_target['spwsel_low_spread'] = low_spread

                if target_ok:
                    clean_list_pending.append(new_target)

            context.clean_list_pending = clean_list_pending

        if aggregated_warnings:
            context.set_condition(
                conditions.CONDITION_CODE_CONTINUUM_SELECTION_WARNING,
                severity='warning',
                scope='stage',
                disposition='continue',
                message='Continuum selection produced %d warning(s).' % (len(aggregated_warnings)),
                details={
                    'warning_count': len(aggregated_warnings),
                    'warnings': aggregated_warnings,
                },
            )
        else:
            context.clear_condition(conditions.CONDITION_CODE_CONTINUUM_SELECTION_WARNING)

        # Remove heuristics objects to avoid accumulating large amounts of unnecessary memory
        for target in self.inputs['target_list']:
            try:
                del target['heuristics']
            except:
                pass

    def __repr__(self):
        repr = 'FindCont:\n'
        for source_name in self.result_cont_ranges:
            repr += ' Source %s\n' % (source_name)
            for spwid in self.result_cont_ranges[source_name]:
                repr += '  SpW %s:' % (spwid)
                if self.result_cont_ranges[source_name][spwid]['cont_ranges']['ranges'] in (['NONE'], []):
                    repr += '   Ranges: None\n'
                elif self.result_cont_ranges[source_name][spwid]['cont_ranges']['ranges'] in (['ALL'], ):
                    repr += '   Ranges: All continuum\n'
                else:
                    repr += '   Ranges: %s' % (';'.join(['%.10f~%.10fGHz' % (float(cont_range['range'][0]), float(cont_range['range'][1])) for cont_range in
                    self.result_cont_ranges[source_name][spwid]['cont_ranges']['ranges'] if isinstance(cont_range, dict)]))
                    refers = numpy.array([cont_range['refer'] for cont_range in self.result_cont_ranges[source_name][spwid]['cont_ranges']['ranges'] if isinstance(cont_range, dict)])
                    if (refers == 'TOPO').all():
                        refer = 'TOPO'
                    elif (refers == 'LSRK').all():
                        refer = 'LSRK'
                    elif (refers == 'SOURCE').all():
                        refer = 'SOURCE'
                    else:
                        refer = 'UNDEFINED'
                    repr += ' ' + refer
                    if 'ALL' in self.result_cont_ranges[source_name][spwid]['cont_ranges']['ranges']:
                        repr += ' (All continuum) \n'
                    else:
                        repr += '\n'
                repr += '   Status: %s\n' % (self.result_cont_ranges[source_name][spwid]['status'])

        return repr
