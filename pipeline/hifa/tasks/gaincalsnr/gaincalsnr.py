import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.hifa.heuristics import snr as snr_heuristics
from pipeline.infrastructure import task_registry

LOG = infrastructure.get_logger(__name__)


class GaincalSnrInputs(vdp.StandardInputs):

    @vdp.VisDependentProperty
    def field(self):
        # Return field names in the current ms that have been
        # observed with the desired intent
        fields = self.ms.get_fields(intent=self.intent)
        fieldids = set(sorted([f.id for f in fields]))
        fieldnames = []
        for fieldid in fieldids:
            field = self.ms.get_fields(field_id=fieldid)
            fieldnames.append(field[0].name)
        field_names = set(fieldnames)
        return ','.join(field_names)

    intent = vdp.VisDependentProperty(default='PHASE')

    @vdp.VisDependentProperty
    def spw(self):

        # Get the science spw ids
        sci_spws = {spw.id for spw in self.ms.get_spectral_windows(science_windows_only=True)}

        # Get the phase spw ids
        phase_spws = []
        for scan in self.ms.get_scans(scan_intent=self.intent):
            phase_spws.extend(spw.id for spw in scan.spws)
        phase_spws = set(phase_spws).intersection(sci_spws)

        # Get science target spw ids
        target_spws = []
        for scan in self.ms.get_scans(scan_intent='TARGET'):
            target_spws.extend([spw.id for spw in scan.spws])
        target_spws = set(target_spws).intersection(sci_spws)

        # Compute the intersection of the bandpass and science target spw
        # ids
        #    Sanity check not reuired for more advanced observingr modes
        spws = list(phase_spws.intersection(target_spws))
        if not spws:
            spws = list(phase_spws)

        spws = [str(spw) for spw in sorted(spws)]
        return ','.join(spws)

    bwedgefrac = vdp.VisDependentProperty(default=0.03125)
    hm_nantennas = vdp.VisDependentProperty(default='unflagged')
    maxfracflagged = vdp.VisDependentProperty(default=0.90)

    # docstring and type hints: supplements hifa_gaincalsnr
    def __init__(self, context, output_dir=None, vis=None, field=None, intent=None, spw=None, bwedgefrac=None,
                 hm_nantennas=None, maxfracflagged=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: The list of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the pipeline context.

                Example: ``vis=['M82A.ms', 'M82B.ms']``

            field: The list of field names of sources to be used for signal to noise
                estimation. Defaults to all fields with the standard intent.

                Example: ``field='3C279'``

            intent: A string containing a comma-delimited list of intents against which
                the selected fields are matched. Defaults to ``'PHASE'``.

                Example: ``intent='BANDPASS'``

            spw: The list of spectral windows and channels for which gain solutions are
                computed. Defaults to all the science spectral windows for which there are
                both 'intent' and TARGET intents.

                Example: ``spw='13,15'``

            bwedgefrac: The fraction of the bandwidth edges that is flagged.

                Example: ``bwedgefrac=0.0``

            hm_nantennas: The heuristics for determines the number of antennas to use
                in the signal to noise estimate. The options are 'all' and 'unflagged'.
                The 'unflagged' options is not currently supported.

                Example: ``hm_nantennas='unflagged'``

            maxfracflagged: The maximum fraction of an antenna that can be flagged
                before it is excluded from the signal to noise estimate.

                Example: ``maxfracflagged=0.80``
        """
        super().__init__()

        self.context = context
        self.vis = vis
        self.output_dir = output_dir

        self.field = field
        self.intent = intent
        self.spw = spw
        self.bwedgefrac = bwedgefrac
        self.hm_nantennas = hm_nantennas
        self.maxfracflagged = maxfracflagged


@task_registry.set_equivalent_casa_task('hifa_gaincalsnr')
class GaincalSnr(basetask.StandardTaskTemplate):
    Inputs = GaincalSnrInputs

    def prepare(self, **parameters):

        # Simplify the inputs
        inputs = self.inputs

        # Turn the CASA field name and spw id lists into Python lists
        fieldlist = inputs.field.split(',')
        spwlist = [int(spw) for spw in inputs.spw.split(',')]

        # Log the data selection choices
        LOG.info('Estimating gaincal solution SNR for MS %s' % inputs.ms.basename)
        LOG.info('    Setting gaincal intent to %s ' % inputs.intent)
        LOG.info('    Selecting gaincal fields %s ' % fieldlist)
        LOG.info('    Selecting gaincal spws %s ' % spwlist)
        if len(fieldlist) <= 0 or len(spwlist) <= 0:
            LOG.info('    No gaincal data')
            return GaincalSnrResults(vis=inputs.vis)

        # Compute the gain SNR values.
        snr_dict = snr_heuristics.estimate_gaincalsnr(
            inputs.ms, fieldlist, inputs.intent, spwlist, inputs.hm_nantennas,
            inputs.maxfracflagged, inputs.bwedgefrac)

        if not snr_dict:
            LOG.info('No SNR dictionary')
            return GaincalSnrResults(vis=inputs.vis)

        # Construct the results object
        result = self._get_results(inputs.vis, spwlist, snr_dict)

        # Return the results
        return result

    def analyse(self, result):
        return result

    # Get final results from the spw dictionary
    @staticmethod
    def _get_results(vis, spwidlist, snr_dict):

        # Initialize result structure.
        result = GaincalSnrResults(vis=vis, spwids=spwidlist)

        # Initialize the lists
        scantimes = []
        inttimes = []
        sensitivities = []
        sensitivitiesint = []
        snrs = []
        snrsint = []

        # Loop over the spws. Values for spws with
        # not dictionary entries are set to None
        for spwid in spwidlist:

            if spwid not in snr_dict:
                scantimes.append(None)
                inttimes.append(None)
                sensitivities.append(None)
                sensitivitiesint.append(None)
                snrs.append(None)
                snrsint.append(None)
            else:
                scantimes.append(snr_dict[spwid]['scantime_minutes'])
                inttimes.append(snr_dict[spwid]['inttime_minutes'])
                sensitivities.append(snr_dict[spwid]['sensitivity_per_scan_mJy'])
                sensitivitiesint.append(snr_dict[spwid]['sensitivity_per_int_mJy'])
                snrs.append(snr_dict[spwid]['snr_per_scan'])
                snrsint.append(snr_dict[spwid]['snr_per_int'])

        # Populate the result.
        result.scantimes = scantimes
        result.inttimes = inttimes
        result.sensitivities = sensitivities
        result.sensitivitiesint = sensitivitiesint
        result.snrs = snrs
        result.snrsint = snrsint 

        return result


# The results class
class GaincalSnrResults(basetask.Results):
    def __init__(self, vis=None, spwids=None):
        """
        Initialise the results object.
        """
        super().__init__()

        self.vis = vis
        if spwids is None:
            spwids = []
        self.spwids = spwids

        self.scantimes = []
        self.inttimes = []
        self.sensitivities = []
        self.sensitivitiesint = []
        self.snrs = []
        self.snrsint = []

    def __repr__(self):
        if self.vis is None or not self.spwids:
            return 'GaincalSnrResults:\n\tNo gaincal SNRs computed'
        else:
            s = f"GaincalSnrResults:\nvis={self.vis}\nGaincal SNRs\n"
            for i in range(len(self.spwids)):
                s += (f"\tspwid {self.spwids[i]:2d}\n"
                      f"\t\tscan-based sensitivity: {self.sensitivities[i]:10.3f}; SNR: {self.snrs[i]:8.3f}\n"
                      f"\t\tintegration-based sensitivity: {self.sensitivitiesint[i]:10.3f}; SNR: {self.snrsint[i]:8.3f}\n")
            return s
