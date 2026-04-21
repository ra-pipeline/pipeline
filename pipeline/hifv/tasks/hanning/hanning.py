# Do not evaluate type annotations at definition time.
from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from pipeline import infrastructure
from pipeline.domain.measures import FrequencyUnits
from pipeline.infrastructure import basetask, casa_tasks, casa_tools, task_registry, vdp
from pipeline.infrastructure.utils import conversion, find_ranges

LOG = infrastructure.logging.get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipeline.infrastructure.api import Results
    from pipeline.infrastructure.jobrequest import JobRequest
    from pipeline.infrastructure.launcher import Context


class HanningInputs(vdp.StandardInputs):
    """Inputs class for the hifv_hanning pipeline smoothing task.  Used on VLA measurement sets.

    The class inherits from vdp.StandardInputs.

    """
    maser_detection = vdp.VisDependentProperty(default=True)
    spws_to_smooth = vdp.VisDependentProperty(default=None)

    # docstring and type hints: supplements hifv_hanning
    def __init__(
            self,
            context: Context,
            vis: str | None = None,
            maser_detection: bool | None = None,
            spws_to_smooth: str | None = None,
            ):
        """
        Args:
            context: Pipeline context

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets specified in the hifv_importdata task.

            maser_detection: Run maser detect algorithm on spectral line windows if spws_to_smooth is None. Defaults to True.

            spws_to_smooth: A CASA-style range of spw IDs indicating which ones to smooth.

                Example: '1,2~4,7' indicates spws 1, 2, 3, 4, and 7 should be smoothed.

        """
        super().__init__()
        self.context = context
        self.vis = vis
        self.maser_detection = maser_detection
        self.spws_to_smooth = spws_to_smooth

        if self.spws_to_smooth is not None:
            self.spws_to_smooth = conversion.range_to_list(self.spws_to_smooth)


class HanningResults(basetask.Results):
    """Results class for the hifv_hanning pipeline smoothing task.  Used on VLA measurement sets.

    The class inherits from basetask.Results

    """
    def __init__(
            self,
            task_successful: bool,
            qa_message: str,
            final: list | None = None,
            pool: list | None = None,
            preceding: list | None = None,
            smoothed_spws: dict[int, tuple[bool, str]] | None = None,
            ):
        """
        Args:
            task_successful: Indicates if the task completed successfully or not.
            qa_message: Information about the outcome of hanningsmooth task to be displayed in the weblog.
            final: Final list of tables (not used in this task)
            pool: Pool list (not used in this task)
            preceding: Preceding list (not used in this task)
            smoothed_spws: Information about spws, including whether they were smoothed and the reason for it.
        """
        if final is None:
            final = []
        if pool is None:
            pool = []
        if preceding is None:
            preceding = []
        if smoothed_spws is None:
            smoothed_spws = {}

        super().__init__()

        self.task_successful = task_successful
        self.qa_message = qa_message
        self.vis = None
        self.pool = pool[:]
        self.final = final[:]
        self.preceding = preceding[:]
        self.error = set()
        self.smoothed_spws = smoothed_spws

    def merge_with_context(self, context: Context) -> None:
        """
        Args:
            context: Pipeline context object
        """
        m = context.observing_run.measurement_sets[0]


@task_registry.set_equivalent_casa_task('hifv_hanning')
class Hanning(basetask.StandardTaskTemplate):
    """Class for the hifv_hanning pipeline smoothing task.  Used on VLA measurement sets.

    The class inherits from basetask.StandardTaskTemplate

    """
    Inputs = HanningInputs

    def prepare(self) -> HanningResults:
        """Method where the hanning smoothing operation is executed.

        The MS SPECTRAL_WINDOW table is examined to see if the SDM_NUM_BIN value is greater than 1.
        If the value is great than 1, then hanning smoothing does not proceed.

        The CASA task hanningsmooth() is executed on the data, creating a temporary measurement set (MS).
        The original MS is removed from disk, and the temporary MS is renamed to the original MS.
        An exception in thrown if an error occurs.

        Returns:
            HanningResults() type object
        """

        with casa_tools.TableReader(self.inputs.vis + '/SPECTRAL_WINDOW') as table:
            if 'OFFLINE_HANNING_SMOOTH' in table.colnames():
                qa_message = "MS has already had offline hanning smoothing applied. Skipping this stage."
                LOG.warning(qa_message)
                return HanningResults(task_successful=True, qa_message=qa_message)

        spws = self.inputs.context.observing_run.get_ms(self.inputs.vis).get_spectral_windows(science_windows_only=True)
        smoothing_dict = {}

        # Smooth input spws only if applicable. Overrides everything else
        if self.inputs.spws_to_smooth is not None:
            for spw in spws:
                if spw.id in self.inputs.spws_to_smooth:
                    smoothing_dict[spw.id] = (True, "restored or user-defined smoothing")
                else:
                    smoothing_dict[spw.id] = (False, "")
        else:
            # Retrieve SPWs information and determine which to smooth
            if not self.inputs.maser_detection:
                LOG.info("Maser detection turned off.")

            # If any spws had online smoothing applied, do not smooth any spws
            if any([spw.sdm_num_bin > 1 for spw in spws]):
                for spw in spws:
                    smoothing_dict[spw.id] = (False, "online smoothing applied")
            else:
                for spw in spws:
                    smoothing_dict[spw.id] = (False, "")
                    if spw.specline_window:
                        if self.inputs.maser_detection and self._checkmaserline(str(spw.id)):
                            smoothing_dict[spw.id] = (True, "spectral line, maser line")
                        else:
                            smoothing_dict[spw.id] = (False, "spectral line")
                    else:
                        smoothing_dict[spw.id] = (True, "continuum")

        hs_dict = {key: val[0] for key, val in smoothing_dict.items()}

        # Update spws_to_smooth if it was automatically calculated (not user-provided)
        if self.inputs.spws_to_smooth is None:
            self.inputs.spws_to_smooth = [spw_id for spw_id, should_smooth in hs_dict.items() if should_smooth]

        task_successful = True
        qa_message = "Hanning smoothing task completed successfully."

        if not any(hs_dict.values()):
            qa_message = "None of the science spectral windows were selected for smoothing."
            LOG.info(qa_message)
            self._track_hsmooth(hs_dict)
            return HanningResults(task_successful=True, qa_message=qa_message, smoothed_spws=smoothing_dict)

        # Only proceed with smoothing if needed
        if all(hs_dict.values()):
            LOG.info("All science spectral windows were selected for hanning smoothing.")
        else:
            smoothing_windows = [str(x) for x, y in hs_dict.items() if y]
            message = find_ranges(smoothing_windows)
            LOG.info("Smoothing spectral window(s) %s.", message)

        try:
            self._do_hanningsmooth()
            temp_ms = 'temphanning.ms'

            # Verify temp MS was created
            if not os.path.exists(temp_ms):
                raise RuntimeError(f'Expected output {temp_ms} was not created')

            LOG.info("Removing original VIS %s", self.inputs.vis)
            shutil.rmtree(self.inputs.vis)

            LOG.info("Renaming %s to %s", temp_ms, self.inputs.vis)
            os.rename(temp_ms, self.inputs.vis)

        except Exception as ex:
            qa_message = f'Problem encountered with hanning smoothing task: {ex}'
            LOG.warning(qa_message)
            task_successful = False

            # Cleanup: if temp MS exists but original is gone, try to restore
            if os.path.exists(temp_ms) and not os.path.exists(self.inputs.vis):
                try:
                    LOG.warning("Attempting to recover by renaming temporary MS")
                    os.rename(temp_ms, self.inputs.vis)
                except Exception as cleanup_ex:
                    LOG.error("Failed to recover MS: %s", cleanup_ex)
            # If both exist, remove temp to avoid confusion
            elif os.path.exists(temp_ms) and os.path.exists(self.inputs.vis):
                try:
                    LOG.info("Removing incomplete temporary MS")
                    shutil.rmtree(temp_ms)
                except Exception as cleanup_ex:
                    LOG.warning("Failed to cleanup temporary MS: %s", cleanup_ex)

        # Adding column to SPECTRAL_WINDOW table to indicate whether the SPW was smoothed (True) or not (False)
        self._track_hsmooth(hs_dict)

        return HanningResults(task_successful=task_successful, qa_message=qa_message, smoothed_spws=smoothing_dict)

    def analyse(self, results: Results) -> Results:
        """Method to analyse the results of the hanning smoothing operation.

        Args:
            results: Results object from the prepare() method.

        Returns:
            The same Results object passed in, unmodified.
        """
        return results

    def _do_hanningsmooth(self) -> Callable[[JobRequest], Results]:
        """Execute the CASA task hanningsmooth

        Returns:
            The `execute` function of an Executor class, which returns a result dictionary
        """

        task = casa_tasks.hanningsmooth(vis=self.inputs.vis,
                                        datacolumn='data',
                                        outputvis='temphanning.ms',
                                        smooth_spw=self.inputs.spws_to_smooth)

        return self._executor.execute(task)

    def _checkmaserline(self, spw: str) -> bool:
        """Confirm if known maser line(s) appear in frequency range of spectral window

        Args:
            spw: spectral window number

        Returns:
            True if maser line may exist in window; False otherwise
        """
        LOG.debug("Checking for maser line contamination in spw %s.", spw)

        def freq_to_vel(rest_freq: float, obs_freq: float) -> float:
            c_kms = 2.99792458e5
            return ((rest_freq - obs_freq) / rest_freq) * c_kms

        maser_dict = {
            'OH (1)': 1612231000,
            'OH (2)': 1665401800,
            'OH (3)': 1667359000,
            'OH (4)': 1720530000,
            'H2O': 22235080000,
            'CH3OH (1)': 6668519200,
            'CH3OH (2)': 1217859700,
            'SiOv0': 43423858000,
            'SiOv1': 43122079000,
            'SiOv2': 42820582000,
            'SiOv3': 42519373000,
            '29SiOv0': 42879916000,
            '30SiOv0': 42373359000,
            'SiS': 18154880000,
        }

        qaTool = casa_tools.quanta
        suTool = casa_tools.synthesisutils

        ms_info = self.inputs.context.observing_run.get_ms(self.inputs.vis)

        if ms_info is None:
            LOG.error("Measurement set %s not found in observing run.", self.inputs.vis)
            return False

        spw_info = ms_info.get_spectral_window(spw)
        freq_low = spw_info._min_frequency.convert_to(newUnits=FrequencyUnits.HERTZ).value
        freq_high = spw_info._max_frequency.convert_to(newUnits=FrequencyUnits.HERTZ).value
        if spw_info._ref_frequency_frame != 'TOPO':
            LOG.info("Spectral window reference frame not TOPO. Skipping maser detection.")
            return False

        to_lsrk = suTool.advisechansel(msname=ms_info.name, spwselection=spw, getfreqrange=True, freqframe='LSRK')
        freq_low = float(qaTool.getvalue(qaTool.convert(to_lsrk['freqstart'], 'Hz'))[0])
        freq_high = float(qaTool.getvalue(qaTool.convert(to_lsrk['freqend'], 'Hz'))[0])
        LOG.debug("Freq low: %f; Freq high: %f", freq_low, freq_high)

        for value in maser_dict.values():
            vel_low = freq_to_vel(value, freq_low)
            vel_high = freq_to_vel(value, freq_high)
            if (freq_low <= value <= freq_high) or abs(vel_low) <= 200 or abs(vel_high) <= 200:
                LOG.info("Maser line possible in spw %s. Hanning smoothing will be applied.", spw)
                return True
        return False

    def _track_hsmooth(self, hs_dict: dict[int, bool]) -> None:
        """Modify SPECTRAL_WINDOW table to track hanning smoothing

        Args:
            hs_dict: hanning smoothing dictionary to write in SPECTRAL_WINDOW table
        """

        LOG.info("Writing Hanning smoothing information to SPECTRAL_WINDOW table of MS %s.", self.inputs.vis)
        desc = {'OFFLINE_HANNING_SMOOTH': {'comment': 'Offline Hanning Smooth Flag',
                            'dataManagerGroup': 'StandardStMan',
                            'dataManagerType': 'StandardStMan',
                            'keywords': {},
                            'maxlen': 0,
                            'option': 0,
                            'valueType': 'boolean'}}
        with casa_tools.TableReader(self.inputs.vis + '/SPECTRAL_WINDOW', nomodify=False) as tb:
            tb.addcols(desc)
            for spw, value in hs_dict.items():
                tb.putcell('OFFLINE_HANNING_SMOOTH', spw, value)
