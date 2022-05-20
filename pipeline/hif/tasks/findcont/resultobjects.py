import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.contfilehandler as contfilehandler

import numpy

LOG = infrastructure.get_logger(__name__)


class FindContResult(basetask.Results):
    def __init__(self, result_cont_ranges, cont_ranges, num_found, num_total, single_range_channel_fractions):
        super(FindContResult, self).__init__()
        self.result_cont_ranges = result_cont_ranges
        self.cont_ranges = cont_ranges
        self.num_found = num_found
        self.num_total = num_total
        self.mitigation_error = False
        self.plot_path = None
        self.single_range_channel_fractions = single_range_channel_fractions

    def merge_with_context(self, context):
        if not self.mitigation_error:
            # write the new ranges to the continuum file
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
                    if new_spw_sel:
                        spwsel = {}
                        for spwid in spwids.split(','):
                            if (self.cont_ranges['fields'][source_name][spwid] == ['NONE']) and (target['intent'] == 'TARGET'):
                                spwsel['spw%s' % (spwid)] = ''
                                LOG.warning('No continuum frequency range information found for %s, spw %s.' % (target['field'], spwid))
                                all_continuum = False
                            elif self.cont_ranges['fields'][source_name][spwid] == ['ALL']:
                                spwsel['spw%s' % (spwid)] = 'ALL'
                            else:
                                new_spwids.append(spwid)
                                spwsel['spw%s' % (spwid)] = ';'.join(['%.10f~%.10fGHz' % (float(cont_range['range'][0]), float(cont_range['range'][1])) for cont_range in self.cont_ranges['fields'][source_name][spwid] if isinstance(cont_range, dict)])
                                refers = numpy.array([cont_range['refer'] for cont_range in self.cont_ranges['fields'][source_name][spwid] if isinstance(cont_range, dict)])
                                if (refers == 'TOPO').all():
                                    refer = 'TOPO'
                                elif (refers == 'LSRK').all():
                                    refer = 'LSRK'
                                elif (refers == 'SOURCE').all():
                                    refer = 'SOURCE'
                                else:
                                    refer = 'UNDEFINED'
                                spwsel['spw%s' % (spwid)] = '%s %s' % (spwsel['spw%s' % (spwid)], refer)
                                if 'ALL' not in self.cont_ranges['fields'][source_name][spwid]:
                                    all_continuum = False

                        new_spwids = ','.join(new_spwids)
                        if (new_spwids == '') and (target['intent'] == 'TARGET'):
                            LOG.warning('No continuum selection for target %s, spw %s. Will not image this selection.' % (
                                new_target['field'], new_target['spw']))
                            target_ok = False
                        else:
                            new_target['spw'] = new_spwids
                            new_target['spwsel_lsrk'] = spwsel
                            new_target['spwsel_all_cont'] = all_continuum

                if target_ok:
                    clean_list_pending.append(new_target)

            context.clean_list_pending = clean_list_pending

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
                if self.result_cont_ranges[source_name][spwid]['cont_ranges'] in (['NONE'], []):
                    repr += '   Ranges: None\n'
                elif self.result_cont_ranges[source_name][spwid]['cont_ranges'] in (['ALL'], ):
                    repr += '   Ranges: All continuum\n'
                else:
                    repr += '   Ranges: %s' % (';'.join(['%.10f~%.10fGHz' % (float(cont_range['range'][0]), float(cont_range['range'][1])) for cont_range in self.result_cont_ranges[source_name][spwid]['cont_ranges'] if isinstance(cont_range, dict)]))
                    refers = numpy.array([cont_range['refer'] for cont_range in self.result_cont_ranges[source_name][spwid]['cont_ranges'] if isinstance(cont_range, dict)])
                    if (refers == 'TOPO').all():
                        refer = 'TOPO'
                    elif (refers == 'LSRK').all():
                        refer = 'LSRK'
                    elif (refers == 'SOURCE').all():
                        refer = 'SOURCE'
                    else:
                        refer = 'UNDEFINED'
                    repr += ' ' + refer
                    if 'ALL' in self.result_cont_ranges[source_name][spwid]['cont_ranges']:
                        repr += ' (All continuum) \n'
                    else:
                        repr += '\n'
                repr += '   Status: %s\n' % (self.result_cont_ranges[source_name][spwid]['status'])

        return repr
