import pipeline.h.tasks.restoredata.restoredata as restoredata
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.vdp as vdp
from pipeline.h.tasks.applycal import applycal
from pipeline.infrastructure import task_registry
from ..importdata import almaimportdata

LOG = infrastructure.get_logger(__name__)


class ALMARestoreDataInputs(restoredata.RestoreDataInputs):
    asis = vdp.VisDependentProperty(
        default='SBSummary ExecBlock Antenna Annotation Station Receiver Source CalAtmosphere CalWVR CalPointing')

    # docstring and type hints: supplements hifa_restoredata
    def __init__(self, context, copytoraw=None, products_dir=None, rawdata_dir=None, output_dir=None, session=None,
                 vis=None, bdfflags=None, lazy=None, asis=None, ocorr_mode=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context.

            copytoraw: Copy calibration and flagging tables from ``products_dir`` to
                ``rawdata_dir`` directory.

                Default: True.

                Example: copytoraw=False

            products_dir: Name of the data products directory to copy calibration
                products from.
                Default: '../products'
                The parameter is effective only when ``copytoraw`` = True.
                When ``copytoraw`` = False, calibration products in
                ``rawdata_dir`` will be used.

                Example: products_dir='myproductspath'

            rawdata_dir: Name of the raw data directory.

                Default: '../rawdata'.

                Example: rawdata_dir='myrawdatapath'

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            session: List of sessions one per visibility file.

                Example: session=['session_3']

            vis: List of raw visibility data files to be restored.
                Assumed to be in the directory specified by rawdata_dir.

                Example: vis=['uid___A002_X30a93d_X43e']

            bdfflags: Set the BDF flags.

                Default: True.

                Example: bdfflags=False

            lazy: Use the lazy filler option.

                Default: False.

                Example: lazy=True

            asis: Creates verbatim copies of the ASDM tables in the output MS.
                The value given to this option must be a string containing a
                list of table names separated by whitespace characters.

                Default: 'SBSummary ExecBlock Antenna Annotation Station Receiver Source CalAtmosphere CalWVR CalPointing'.

                Example: asis='Source Receiver'

            ocorr_mode: Set ocorr_mode.

                Default: 'ca'.

                Example: ocorr_mode='ca'

        """
        super(ALMARestoreDataInputs, self).__init__(context, copytoraw=copytoraw, products_dir=products_dir,
                                                    rawdata_dir=rawdata_dir, output_dir=output_dir, session=session,
                                                    vis=vis, bdfflags=bdfflags, lazy=lazy, asis=asis,
                                                    ocorr_mode=ocorr_mode)


@task_registry.set_equivalent_casa_task('hifa_restoredata')
class ALMARestoreData(restoredata.RestoreData):
    Inputs = ALMARestoreDataInputs

    # Override generic method and use an ALMA specific one. Not much difference
    # now but should simplify parameters in future
    def _do_importasdm(self, sessionlist, vislist):
        inputs = self.inputs

        container = vdp.InputsContainer(almaimportdata.ALMAImportData, inputs.context, vis=vislist, session=sessionlist,
                                        save_flagonline=False, lazy=inputs.lazy, bdfflags=inputs.bdfflags,
                                        dbservice=False, asis=inputs.asis, ocorr_mode=inputs.ocorr_mode)
        importdata_task = almaimportdata.ALMAImportData(container)
        return self._executor.execute(importdata_task, merge=True)

    # Override generic method for an ALMA specific one.
    def _do_applycal(self):
        # PIPE-1165: for hifa_applycal, include the polarization intents.
        container = vdp.InputsContainer(applycal.SerialApplycal, self.inputs.context,
                                        intent='TARGET,PHASE,BANDPASS,AMPLITUDE,CHECK,POLARIZATION,POLANGLE,POLLEAKAGE')

        # PIPE-1973: check whether any of the caltables-to-be-applied were
        # produced by hifa_polcal, and if so, ensure that applycal is called
        # with parang=True.
        try:
            hifa_polcal_found = self._check_for_hifa_polcal_tables(container)
            if hifa_polcal_found:
                LOG.info("Found hifa_polcal produced caltable(s) to be applied: will call applycal with parang=True.")
                container.parang = True
        except:
            LOG.info("Unable to determine if any hifa_polcal produced caltable(s) are to be applied; will not modify"
                     " value for 'parang'.")

        # Create task, and return result from executing task.
        applycal_task = applycal.SerialApplycal(container)
        return self._executor.execute(applycal_task, merge=True)

    def _check_for_hifa_polcal_tables(self, inputs_container):
        """
        Utility method to determine whether a hifa_polcal produced caltable
        is present in the context callibrary.
        """
        # Perform check for each set of inputs (i.e. per MS).
        hifa_polcal_found = False
        for inputs in inputs_container:
            # Get the target data selection for this task as a CalTo object and
            # retrieve corresponding CalState.
            calto = callibrary.get_calto_from_inputs(inputs)
            calstate = self.inputs.context.callibrary.get_calstate(calto)

            # Determine whether any caltable-to-be-applied was created by
            # hifa_polcal.
            if any('.hifa_polcal.' in calfrom.gaintable for _, calfroms in calstate.merged().items()
                   for calfrom in calfroms):
                hifa_polcal_found = True
                break

        return hifa_polcal_found
