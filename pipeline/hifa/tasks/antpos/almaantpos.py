import pipeline.hif.tasks.antpos.antpos as antpos
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import task_registry

__all__ = [
    'ALMAAntpos',
    'ALMAAntposInputs'
]

LOG = infrastructure.get_logger(__name__)


class ALMAAntposInputs(antpos.AntposInputs):
    """
    ALMAAntposInputs defines the inputs for the ALMAAntpos pipeline task.
    """
    # These are ALMA specific settings and override the defaults in
    # the base class.

    # Force the offset input to be from a file
    hm_antpos = vdp.VisDependentProperty(default='file')
    threshold = vdp.VisDependentProperty(default=1.0)

    # docstring and type hints: supplements hifa_antpos
    def __init__(self, context, output_dir=None, vis=None, caltable=None, hm_antpos=None, antposfile=None, antenna=None,
                 offsets=None, threshold=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: List of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the pipeline context.

                Example: vis=['ngc5921.ms']

            caltable: List of names for the output calibration tables. Defaults
                to the standard pipeline naming convention.

                Example: caltable=['ngc5921.gcal']

            hm_antpos: Heuristics method for retrieving the antenna position
                corrections. The options are 'online' (not yet implemented),
                'manual', and 'file'.

                Example: hm_antpos='manual'

            antposfile: The file(s) containing the antenna offsets. Used if
                ``hm_antpos`` is 'file'.

            antenna: The list of antennas for which the positions are to be corrected
                if ``hm_antpos`` is 'manual'.

                Example: antenna='DV05,DV07'

            offsets: The list of antenna offsets for each antenna in 'antennas'.
                Each offset is a set of 3 floating point numbers separated by
                commas, specified in the ITRF frame.

                Example: offsets=[0.01, 0.02, 0.03, 0.03, 0.02, 0.01]

            threshold: Highlight antenna position offsets greater than this value in
                the weblog. Units are wavelengths and the default is 1.0.

                Example: threshold=1.0

        """
        super(ALMAAntposInputs, self).__init__(
            context, output_dir=output_dir, vis=vis, caltable=caltable, hm_antpos=hm_antpos, antposfile=antposfile,
            antenna=antenna, offsets=offsets)
        self.threshold = threshold

    def __str__(self):
        s = 'AlmaAntposInputs:\n'
        s += '\tvis: %s\n' % self.vis
        s += '\tcaltable: %s\n' % self.caltable
        s += '\thm_antpos: %s\n' % self.hm_antpos
        s += '\tantposfile: %s\n' % self.antposfile
        s += '\tantenna: %s\n' % self.antenna
        s += '\toffsets: %s\n' % self.offsets
        s += '\tthreshold: %s\n' % self.threshold
        return s

@task_registry.set_equivalent_casa_task('hifa_antpos')
class ALMAAntpos(antpos.Antpos):
    Inputs = ALMAAntposInputs
