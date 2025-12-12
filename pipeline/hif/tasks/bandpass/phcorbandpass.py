import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import casa_tools

from .. import gaincal
from . import bandpassmode, bandpassworker

LOG = infrastructure.get_logger(__name__)


class PhcorBandpassInputs(bandpassmode.BandpassModeInputs):

    phaseup = vdp.VisDependentProperty(default=True)
    phaseupbw = vdp.VisDependentProperty(default='')
    phaseupsolint = vdp.VisDependentProperty(default='int')
    solint = vdp.VisDependentProperty(default='inf')

    def __init__(self, context, mode=None, phaseup=None, phaseupbw=None, phaseupsolint=None,
                 solint=None, **parameters):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            mode: Effectively unused. Fixed to 'channel' in implementation.

            phaseup: Do a phaseup on the data before computing the bandpass solution.

            phaseupbw: Bandwidth to be used for phaseup. Defaults to 500MHz. Used when phaseup is True.

                Examples: phaseupbw='' to use entire bandpass
                phaseupbw='500MHz' to use central 500MHz

            phaseupsolint: The phase correction solution interval in CASA syntax. Used when phaseup is True.

                Example: phaseupsolint=300

            solint: Time and channel solution intervals in CASA syntax.

                Examples: solint='inf,10ch', solint='inf'

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets specified in the <hifa,hifv>_importdata task.
                '': use all MeasurementSets in the context
                Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']

            caltable: The list of output calibration tables. Defaults to the standard pipeline naming convention.
                Example: caltable=['M82.gcal', 'M82B.gcal']

            field: The list of field names or field ids for which bandpasses are computed. Defaults to all fields.
                Examples: field='3C279', field='3C279, M82'

            intent: A string containing a comma delimited list of intents against which the selected fields are matched.  Defaults to all data
                with bandpass intent.
                Example: intent='`*PHASE*`'

            spw: The list of spectral windows and channels for which bandpasses are computed. Defaults to all science spectral windows.
                Example: spw='11,13,15,17'

            antenna: Set of data selection antenna IDs

            combine: Data axes to combine for solving. Axes are '', 'scan', 'spw', 'field' or any comma-separated combination.
                Example: combine='scan,field'

            refant: Reference antenna names. Defaults to the value(s) stored in the pipeline context. If undefined in the pipeline context
                defaults to the CASA reference antenna naming scheme.
                Examples: refant='DV01', refant='DV06,DV07'

            solnorm: Normalise the bandpass solution

            minblperant: Minimum number of baselines required per antenna for each solve. Antennas with fewer baselines are excluded from
                solutions.

            minsnr: Reject solutions below this SNR
        """
        super().__init__(context, mode='channel', phaseup=phaseup, phaseupbw=phaseupbw,
                         phaseupsolint=phaseupsolint, solint=solint, **parameters)


class PhcorBandpass(bandpassworker.BandpassWorker):
    Inputs = PhcorBandpassInputs

    def prepare(self, **parameters):
        inputs = self.inputs

        # if requested, execute a phaseup job. This will add the resulting
        # caltable to the on-the-fly calibration context, so we don't need any
        # subsequent gaintable manipulation
        if inputs.phaseup:
            phaseup_result = self._do_phaseup()

        # Now perform the bandpass
        result = self._do_bandpass()

        # Attach the preparatory result to the final result so we have a
        # complete log of all the executed tasks.
        if inputs.phaseup:
            result.preceding.append(phaseup_result.final)

        return result

    def _do_phaseup(self):
        inputs = self.inputs

        phaseup_inputs = gaincal.GTypeGaincal.Inputs(inputs.context,
            vis         = inputs.vis,
            field       = inputs.field,
            spw         = self._get_phaseup_spw(),
            antenna     = inputs.antenna,
            intent      = inputs.intent,
            solint      = inputs.phaseupsolint,
            refant      = inputs.refant,
            minblperant = inputs.minblperant,
            calmode     = 'p',
            minsnr      = inputs.minsnr)

        phaseup_task = gaincal.GTypeGaincal(phaseup_inputs)

        result = self._executor.execute(phaseup_task, merge=False)
        if not result.final:
            LOG.warning('No bandpass phaseup solution computed for %s' % (inputs.ms.basename))
        else:
            result.accept(inputs.context)
        return result

    def _do_bandpass(self):
        bandpass_task = bandpassmode.BandpassMode(self.inputs)
        return self._executor.execute(bandpass_task)

    def _get_phaseup_spw(self):
        '''
                   ms -- measurement set object
               spwstr -- comma delimited list of spw ids
            bandwidth -- bandwidth in Hz of central channels used to
                         phaseup
        '''
        inputs = self.inputs

        # Add the channel ranges in. Note that this currently assumes no prior
        # channel selection.
        if inputs.phaseupbw == '':
            return inputs.spw

        # Convert bandwidth input to CASA quantity and then on to pipeline
        # domain Frequency object
        quanta = casa_tools.quanta
        bw_quantity = quanta.convert(quanta.quantity(inputs.phaseupbw), 'Hz')
        bandwidth = measures.Frequency(quanta.getvalue(bw_quantity)[0],
                                       measures.FrequencyUnits.HERTZ)

        # Loop over the spws creating a new list with channel ranges
        outspw = []
        for spw in self.inputs.ms.get_spectral_windows(self.inputs.spw):
            cen_freq = spw.centre_frequency
            lo_freq = cen_freq - bandwidth / 2.0
            hi_freq = cen_freq + bandwidth / 2.0
            minchan, maxchan = spw.channel_range(lo_freq, hi_freq)
            cmd = '{0}:{1}~{2}'.format(spw.id, minchan, maxchan)
            outspw.append(cmd)

        return ','.join(outspw)
