import os
import string

from casatasks.private import flaghelper

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.infrastructure import casa_tasks, task_registry
from pipeline.infrastructure.filenamer import sanitize_for_ms

LOG = infrastructure.get_logger(__name__)


class FlagtargetsdataInputs(vdp.StandardInputs):
    """Inputs class for the hifv_flagtargetsdata pipeline task.  Used on VLA measurement sets.

    The class inherits from vdp.StandardInputs.

    """
    # Search order of input vis
    processing_data_type = [DataType.REGCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_ALL, DataType.RAW]

    flagbackup = vdp.VisDependentProperty(default=True)
    template = vdp.VisDependentProperty(default=True)

    @vdp.VisDependentProperty
    def filetemplate(self):
        vis_root = sanitize_for_ms(self.vis)
        return vis_root + '.flagtargetstemplate.txt'

    @filetemplate.convert
    def filetemplate(self, value):
        if isinstance(value, str):
            return list(value.replace('[', '').replace(']', '').replace("'", "").split(','))
        else:
            return value

    @vdp.VisDependentProperty
    def inpfile(self):
        vis_root = sanitize_for_ms(self.vis)
        return os.path.join(self.output_dir, vis_root + '.flagtargetscmds.txt')

    def __init__(self, context, vis=None, output_dir=None, flagbackup=None, template=None, filetemplate=None):
        """
        Args:
            vis(str): String name of the measurement set
            output_dir(str):  Output directory
            flagbackup(bool):  Back up flags or not
            template(bool):  Used template or not
            flagtemplate(str):  String filename of the flagging template to use
        """

        super(FlagtargetsdataInputs, self).__init__()

        self.context = context
        self.vis = vis
        self.output_dir = output_dir

        self.flagbackup = flagbackup
        self.template = template
        self.filetemplate = filetemplate

    def to_casa_args(self):
        """
        Translate the input parameters of this class to task parameters
        required by the CASA task flagdata. The returned object is a
        dictionary of flagdata arguments as keyword/value pairs.

        Return:
            Dict: dictionary of CASA task inputs
        """
        return {'vis': self.vis,
                'mode': 'list',
                'action': 'apply',
                'inpfile': self.inpfile,
                'flagbackup': self.flagbackup}


class FlagtargetsdataResults(basetask.Results):
    """Results class for the hifv_flagtargetsdata pipeline task.  Used on VLA measurement sets.

    The class inherits from basetask.Results.

    """
    def __init__(self, summaries, flagcmds):
        """
        Args:
            summaries(dict):  Flagging summaries
            flagcmds(List):  List of string flagging commands
        """
        super(FlagtargetsdataResults, self).__init__()
        self.pipeline_casa_task = 'Flagtargetsdata'
        self.summaries = summaries
        self._flagcmds = flagcmds

    def flagcmds(self):
        return self._flagcmds

    def merge_with_context(self, context):
        """
        See :method:`~pipeline.infrastructure.api.Results.merge_with_context`
        """
        pass

    def __repr__(self):
        # Step through the summary list and print a few things.
        # SUBTRACT flag counts from previous agents, because the counts are
        # cumulative.
        s = 'Flagtargetsdata flagging results:\n'

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


@task_registry.set_equivalent_casa_task('hifv_flagtargetsdata')
@task_registry.set_casa_commands_comment('Flagtargetsdata')
class Flagtargetsdata(basetask.StandardTaskTemplate):
    """Class for the hifv_flagtargetsdata pipeline task.  Used on VLA measurement sets.

    The class inherits from basetask.StandardTaskTemplate

    """
    Inputs = FlagtargetsdataInputs

    def prepare(self):

        inputs = self.inputs

        flag_cmds = self._get_flag_commands()
        flag_str = '\n'.join(flag_cmds)

        with open(inputs.inpfile, 'w') as stream:
            stream.writelines(flag_str)

        LOG.debug('Flag commands for %s:\n%s', inputs.vis, flag_str)

        # Map the pipeline inputs to a dictionary of CASA task arguments
        task_args = inputs.to_casa_args()

        # create and execute a flagdata job using these task arguments
        job = casa_tasks.flagdata(**task_args)
        summary_dict = self._executor.execute(job)

        agent_summaries = dict((v['name'], v) for v in summary_dict.values())

        ordered_agents = ['before', 'template']

        summary_reps = [agent_summaries[agent]
                        for agent in ordered_agents
                        if agent in agent_summaries]

        return FlagtargetsdataResults(summary_reps, flag_cmds)

    def analyse(self, results):
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


