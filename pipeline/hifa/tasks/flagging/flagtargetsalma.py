import os
import re
import string

from casatasks.private import flaghelper

import pipeline.infrastructure as infrastructure
#import pipeline.infrastructure.api as api
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import task_registry
import pipeline.infrastructure.sessionutils as sessionutils

# the logger for this module
LOG = infrastructure.get_logger(__name__)

__all__ = [
    'FlagTargetsALMA',
    'FlagTargetsALMAInputs',
    'FlagTargetsALMAResults'
]


"""
Flag ALMA target science target data.
"""


class FlagTargetsALMAInputs(vdp.StandardInputs):
    """Manages the inputs for the FlagTargetsALMA task.

    Attributes:
        context: The pipeline context holding all pipeline state.
        vis: String or list of strings containing the MS name(s) on which to operate.
        output_dir: The directory to which pipeline data should be sent.
        flagbackup: Whether existing flags should be backed up before new flagging begins.
        template: Whether flagging templates are to be applied.
        filetemplate: The filename of the ASCII file that contains the flagging template.
    """
    # Search order of input vis
    processing_data_types = [DataType.REGCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_ALL, DataType.RAW]

    flagbackup = vdp.VisDependentProperty(default=False)
    template = vdp.VisDependentProperty(default=True)

    @vdp.VisDependentProperty
    def filetemplate(self):
        # PIPE-3003 fixed the template name. The previously used sanitize_for_ms
        # method always used the original MS name template. Thus changing to
        # the real MS root name.
        vis_root = os.path.splitext(os.path.basename(self.vis))[0]
        template = vis_root + '.flagtargetstemplate.txt'
        output_dir = getattr(self, 'output_dir', None) or ''

        def _resolve(filename):
            if os.path.exists(filename):
                return filename
            if output_dir and os.path.exists(os.path.join(output_dir, filename)):
                return os.path.join(output_dir, filename)
            return None

        resolved = _resolve(template)
        if resolved:
            return resolved

        if hasattr(self, 'ms') and self.ms:
            # Check if this is a SubMS slice or logical MS, falling back to parent/origin MS template
            candidates = []
            if hasattr(self.ms, 'parent_ms') and self.ms.parent_ms:
                parent_root = os.path.splitext(os.path.basename(self.ms.parent_ms.name))[0]
                candidates.append(parent_root + '.flagtargetstemplate.txt')
            origin = getattr(self.ms, 'origin_ms', None)
            if origin:
                origin_name = getattr(origin, 'name', origin) if not isinstance(origin, str) else origin
                origin_root = os.path.splitext(os.path.basename(origin_name))[0]
                candidates.append(origin_root + '.flagtargetstemplate.txt')
                candidates.append(origin_root + '_targets.flagtargetstemplate.txt')
            for candidate in candidates:
                cand_resolved = _resolve(candidate)
                if cand_resolved:
                    return cand_resolved

        return os.path.join(output_dir, template) if output_dir and os.path.exists(os.path.join(output_dir, template)) else template

    @vdp.VisDependentProperty
    def inpfile(self):
        vis_root = os.path.splitext(os.path.basename(self.vis))[0]
        return os.path.join(self.output_dir, vis_root + '.flagtargetscmds.txt')

    parallel = sessionutils.parallel_inputs_impl(default=False)

    # docstring and type hints: supplements hifa_flagtargets
    def __init__(self, context, vis=None, output_dir=None, flagbackup=None, template=None, filetemplate=None, parallel=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            vis: The list of input MeasurementSets. Defaults to the list
                of MeasurementSets defined in the pipeline context.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            flagbackup: Back up any pre-existing flags; defaults to False.

            template: Apply flagging templates; defaults to True.

            filetemplate: Text file containing flagging commands for science target data.
                If undefined, defaults to the dataset parent MS name (usually based on uid)
                with '.flagtargetstemplate.txt' suffix.

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

        self.flagbackup = flagbackup
        self.template = template
        self.filetemplate = filetemplate
        self.parallel = parallel

    def to_casa_args(self):
        """
        Translate the input parameters of this class to task parameters
        required by the CASA task flagdata. The returned object is a
        dictionary of flagdata arguments as keyword/value pairs.

        :rtype: dict
        """
        return {'vis': self.vis,
                'mode': 'list',
                'action': 'apply',
                'inpfile': self.inpfile,
                'flagbackup': self.flagbackup}


# tell the infrastructure to prefentially apply the targets
# flags to the split MS(s)
#api.ImagingMeasurementSetsPreferred.register(FlagTargetsALMAInputs)


class FlagTargetsALMAResults(basetask.Results):
    def __init__(self, summaries, flagcmds):
        super().__init__()
        self.summaries = summaries
        self._flagcmds = flagcmds

    def flagcmds(self):
        return self._flagcmds

    def merge_with_context(self, context):
        # nothing to do
        pass

    def __repr__(self):
        # Step through the summary list and print a few things.
        # SUBTRACT flag counts from previous agents, because the counts are
        # cumulative.
        s = 'Target flagging results:\n'

        for idx in range(0, len(self.summaries)):
            flagcount = int(self.summaries[idx]['flagged'])
            totalcount = int(self.summaries[idx]['total'])

            # From the second summary onwards, subtract counts from the previous
            # one
            if idx > 0:
                flagcount = flagcount - int(self.summaries[idx-1]['flagged'])

            s += '\tSummary %s (%s) :  Flagged : %s out of %s (%0.2f%%)\n' % (
                    idx, self.summaries[idx]['name'], flagcount, totalcount,
                    100.0*flagcount/totalcount)

        return s



class SerialFlagTargetsALMA(basetask.StandardTaskTemplate):
    """
    FlagTargetsALMA is a class for target flagging. It can perform

    - Template flags

    """

    # link the accompanying inputs to this task
    Inputs = FlagTargetsALMAInputs

    def prepare(self):
        """
        Prepare and execute a flagdata flagging job appropriate to the
        task inputs.

        """
        # create a local alias for inputs, so we're not saying 'self.inputs'
        # everywhere
        inputs = self.inputs

        # Check if the target MS is an in-memory logical MS or represents on-disk SubMS slices
        is_logical = getattr(inputs.ms, 'is_logical', False) or (
            not os.path.exists(inputs.vis) and getattr(inputs.ms, 'has_subms', lambda: False)()
        )
        if is_logical and getattr(inputs.ms, 'has_subms', lambda: False)():
            return self._prepare_logical_ms()

        # get the flagdata command string required for the results
        flag_cmds = self._get_flag_commands()
        flag_str = '\n'.join(flag_cmds)

        # write the flag commands to the file
        with open(inputs.inpfile, 'w') as stream:
            stream.writelines(flag_str)

        # to save inspecting the file, also log the flag commands
        LOG.debug('Flag commands for %s:\n%s', inputs.vis, flag_str)

        # Map the pipeline inputs to a dictionary of CASA task arguments
        task_args = inputs.to_casa_args()

        # create and execute a flagdata job using these task arguments
        executor = getattr(self, '_executor', None) or basetask.Executor(inputs.context)
        job = casa_tasks.flagdata(**task_args)
        summary_dict = executor.execute(job)

        agent_summaries = dict((v['name'], v) for v in summary_dict.values())

        ordered_agents = ['before', 'template']

        summary_reps = [agent_summaries[agent]
                        for agent in ordered_agents
                        if agent in agent_summaries]

        # return the results object, which will be used for the weblog
        return FlagTargetsALMAResults(summary_reps, flag_cmds)

    def _prepare_logical_ms(self):
        """Prepare and execute flagdata jobs across all component SubMS slices of a logical MS."""
        inputs = self.inputs
        sub_mses = inputs.ms.get_subms()

        flag_cmds = self._get_flag_commands()
        flag_str = '\n'.join(flag_cmds)

        # Write overall parent flag commands file for logging and weblog archive
        with open(inputs.inpfile, 'w') as stream:
            stream.writelines(flag_str)

        LOG.info('Executing flagdata across %d SubMS slice(s) for logical MS %s', len(sub_mses), inputs.ms.basename)
        LOG.debug('Flag commands for %s:\n%s', inputs.vis, flag_str)

        output_dir = inputs.output_dir or ''
        merged_summary_dict = {}
        executor = getattr(self, '_executor', None) or basetask.Executor(inputs.context)

        for sub_ms in sub_mses:
            sub_cmds = self._filter_flag_commands_for_subms(flag_cmds, sub_ms)
            sub_root = os.path.splitext(sub_ms.basename)[0]
            sub_inpfile = os.path.join(output_dir, f"{sub_root}.flagtargetscmds.txt")
            with open(sub_inpfile, 'w') as stream:
                stream.writelines('\n'.join(sub_cmds))

            task_args = {
                'vis': sub_ms.name,
                'mode': 'list',
                'action': 'apply',
                'inpfile': sub_inpfile,
                'flagbackup': inputs.flagbackup,
            }

            job = casa_tasks.flagdata(**task_args)
            sub_summary_dict = executor.execute(job)
            self._merge_flagdata_summaries(merged_summary_dict, sub_summary_dict, sub_ms)

        agent_summaries = dict((v['name'], v) for v in merged_summary_dict.values())
        ordered_agents = ['before', 'template']
        summary_reps = [agent_summaries[agent] for agent in ordered_agents if agent in agent_summaries]

        return FlagTargetsALMAResults(summary_reps, flag_cmds)

    @staticmethod
    def _filter_flag_commands_for_subms(flag_cmds, sub_ms):
        """Filter and adapt flagging commands for a component SubMS slice.

        Args:
            flag_cmds: List of flag command strings.
            sub_ms: The SubMS domain object.

        Returns:
            List of command strings applicable to this SubMS slice.
        """
        sub_cmds = []
        for cmd in flag_cmds:
            # Summary commands apply to all slices
            if "mode='summary'" in cmd or 'mode="summary"' in cmd:
                sub_cmds.append(cmd)
                continue

            # Check field match
            field_match = re.search(r"field=['\"]([^'\"]+)['\"]", cmd)
            if field_match:
                specified_fields = [f.strip() for f in field_match.group(1).split(',')]
                if hasattr(sub_ms, 'matches_field'):
                    if not any(sub_ms.matches_field(f) for f in specified_fields):
                        continue
                else:
                    src_name = getattr(sub_ms, 'source_name', None)
                    field_names = [f.name for f in sub_ms.get_fields()] if hasattr(sub_ms, 'get_fields') else []
                    field_ids = [str(f.id) for f in sub_ms.get_fields()] if hasattr(sub_ms, 'get_fields') else []
                    if src_name:
                        field_names.append(src_name)
                    if not any(sf in field_names or sf in field_ids for sf in specified_fields):
                        continue

            # Check spw match
            spw_match = re.search(r"spw=['\"]([^'\"]+)['\"]", cmd)
            if spw_match:
                specified_spw = spw_match.group(1)
                spw_tokens = [tok.strip() for tok in specified_spw.split(',')]

                matching_tokens = []
                for tok in spw_tokens:
                    base_id = tok.split(':')[0].strip()
                    chan_sel = tok[len(base_id):] if ':' in tok else ''
                    if hasattr(sub_ms, 'matches_spw') and sub_ms.matches_spw(base_id):
                        matching_tokens.append(f"{sub_ms.to_local_spw(base_id)}{chan_sel}")
                    elif not hasattr(sub_ms, 'matches_spw'):
                        real_spw = getattr(sub_ms, 'real_spw_id', None)
                        virt_spw = getattr(sub_ms, 'virtual_spw_id', None)
                        if base_id.isdigit() and (
                            (real_spw is not None and int(base_id) == real_spw)
                            or (virt_spw is not None and int(base_id) == virt_spw)
                        ):
                            matching_tokens.append(f"0{chan_sel}")
                        elif real_spw is None and virt_spw is None:
                            matching_tokens.append(tok)

                if not matching_tokens:
                    continue

                new_spw_spec = ','.join(matching_tokens)
                cmd = re.sub(r"spw=['\"][^'\"]+['\"]", f"spw='{new_spw_spec}'", cmd)

            sub_cmds.append(cmd)

        return sub_cmds

    @staticmethod
    def _merge_flagdata_summaries(accum_dict, sub_summary_dict, sub_ms):
        """Merge a SubMS flagdata summary dictionary into an accumulated summary dictionary.

        Args:
            accum_dict: Accumulated summary dictionary (keyed by report ID, e.g. 'report0').
            sub_summary_dict: Summary dictionary returned from flagdata on sub_ms.
            sub_ms: The SubMS domain object for this slice.
        """
        if not sub_summary_dict or not isinstance(sub_summary_dict, dict):
            return

        spw_map = {}
        if getattr(sub_ms, 'real_spw_id', None) is not None:
            spw_map['0'] = str(sub_ms.real_spw_id)
            spw_map[0] = str(sub_ms.real_spw_id)

        name_to_key = {rep['name']: k for k, rep in accum_dict.items() if isinstance(rep, dict) and 'name' in rep}

        for sub_key, sub_rep in sub_summary_dict.items():
            if not isinstance(sub_rep, dict) or 'name' not in sub_rep:
                continue
            rep_name = sub_rep['name']
            if rep_name in name_to_key:
                target_rep = accum_dict[name_to_key[rep_name]]
            else:
                target_rep = {
                    'name': rep_name,
                    'type': sub_rep.get('type', 'summary'),
                    'flagged': 0.0,
                    'total': 0.0,
                }
                accum_dict[sub_key] = target_rep
                name_to_key[rep_name] = sub_key

            target_rep['flagged'] += float(sub_rep.get('flagged', 0.0))
            target_rep['total'] += float(sub_rep.get('total', 0.0))

            breakdown_keys = ['scan', 'antenna', 'field', 'correlation', 'observation', 'array', 'spw']
            for cat in breakdown_keys:
                if cat not in sub_rep or not isinstance(sub_rep[cat], dict):
                    continue
                if cat not in target_rep:
                    target_rep[cat] = {}

                for item_key, item_val in sub_rep[cat].items():
                    if not isinstance(item_val, dict):
                        continue
                    target_item_key = item_key
                    if cat == 'spw' and item_key in spw_map:
                        target_item_key = spw_map[item_key]

                    if target_item_key in target_rep[cat]:
                        target_rep[cat][target_item_key]['flagged'] += float(item_val.get('flagged', 0.0))
                        target_rep[cat][target_item_key]['total'] += float(item_val.get('total', 0.0))
                    else:
                        target_rep[cat][target_item_key] = {
                            'flagged': float(item_val.get('flagged', 0.0)),
                            'total': float(item_val.get('total', 0.0)),
                        }

    def analyse(self, results):
        """
        Analyse the results of the flagging operation.

        This method does not perform any analysis, so the results object is
        returned exactly as-is, with no data massaging or results items
        added. If additional statistics needed to be calculated based on the
        post-flagging state, this would be a good place to do it.
        """
        return results

    def _get_flag_commands(self):
        """
        Get the flagging commands as a string suitable for flagdata.
        """
        # create a local variable for the inputs associated with this instance
        inputs = self.inputs

        # create list which will hold the flagging commands
        flag_cmds = ["mode='summary' name='before'"]

        # flag template?
        if inputs.template:
            if not os.path.exists(inputs.filetemplate):
                LOG.warning('Template flag file \'%s\' for \'%s\' not found.'
                            % (inputs.filetemplate, inputs.ms.basename))
            else:
                flag_cmds.extend(self._read_flagfile(inputs.filetemplate))
            flag_cmds.append("mode='summary' name='template'")

        return flag_cmds

    @staticmethod
    def _read_flagfile(filename):
        if not os.path.exists(filename):
            LOG.warning('%s does not exist' % filename)
            return []

        # strip out comments and empty lines to leave the real commands.
        # This is so we can compare the number of valid commands to the number
        # of commands specified in the file and complain if they differ
        return [cmd for cmd in flaghelper.readFile(filename)
                if not cmd.strip().startswith('#')
                and not all(c in string.whitespace for c in cmd)]


@task_registry.set_equivalent_casa_task('hifa_flagtargets')
class FlagTargetsALMA(sessionutils.ParallelTemplate):

    Inputs = FlagTargetsALMAInputs
    Task = SerialFlagTargetsALMA
