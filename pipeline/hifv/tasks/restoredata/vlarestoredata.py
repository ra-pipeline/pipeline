import os
import shutil
import tarfile

from packaging.version import parse

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.vdp as vdp
from pipeline.h.tasks.restoredata import restoredata
from pipeline.infrastructure import casa_tasks, task_registry, utils
from pipeline.infrastructure.utils import conversion

from ..finalcals import applycals
from ..hanning import hanning
from ..importdata import importdata

LOG = infrastructure.get_logger(__name__)


class VLARestoreDataInputs(restoredata.RestoreDataInputs):
    bdfflags = vdp.VisDependentProperty(default=False)
    ocorr_mode = vdp.VisDependentProperty(default='co')
    asis = vdp.VisDependentProperty(default='Receiver CalAtmosphere')
    gainmap = vdp.VisDependentProperty(default=False)

    # docstring and type hints: supplements hifv_restoredata
    def __init__(self, context, copytoraw=None, products_dir=None, rawdata_dir=None,
                 output_dir=None, session=None, vis=None, bdfflags=None, lazy=None, asis=None,
                 ocorr_mode=None, gainmap=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            copytoraw: Copy calibration and flagging tables from ``products_dir`` to ``rawdata_dir`` directory.

                Default: ``True``

                Example: ``copytoraw=False``.

            products_dir: Name of the data products directory to copy calibration products from.

                Default: ``'../products'``

                The parameter is effective only when ``copytoraw`` = True.
                When ``copytoraw`` = False, calibration products in
                ``rawdata_dir`` will be used.

                Example: ``products_dir='myproductspath'``

            rawdata_dir: Name of the raw data directory. Default: ``'../rawdata'``

                Example: ``rawdata_dir='myrawdatapath'``

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            session: List of sessions one per visibility file.

                Example: ``session=['session_3']``

            vis: List of visibility data files. These may be ASDMs, tar files of ASDMs, MSes, or tar files of MSes, If ASDM files are specified, they will be
                converted  to MS format.

                Example: ``vis=['X227.ms', 'asdms.tar.gz']``

            bdfflags: Set the BDF flags. Default: False

            lazy: Use the lazy filler option. Default: False

            asis: List of tables to import asis.

                Default: ``'Receiver CalAtmosphere'``

            ocorr_mode: Correlation import mode.

                Default: ``'co'``

            gainmap: If True, map gainfields to a particular list of scans when applying calibration tables.

                Default: ``False``

        """
        super().__init__(context, copytoraw=copytoraw,
                         products_dir=products_dir, rawdata_dir=rawdata_dir,
                         output_dir=output_dir, session=session,
                         vis=vis, bdfflags=bdfflags, lazy=lazy, asis=asis,
                         ocorr_mode=ocorr_mode)

        self.gainmap = gainmap

@task_registry.set_equivalent_casa_task('hifv_restoredata')
class VLARestoreData(restoredata.RestoreData):

    Inputs = VLARestoreDataInputs

    def prepare(self):
        """
        Prepare and execute an export data job appropriate to the
        task inputs.
        """
        # Create a local alias for inputs, so we're not saying
        # 'self.inputs' everywhere
        inputs = self.inputs

        # Force inputs.vis and inputs.session to be a list.
        sessionlist = inputs.session
        if isinstance(sessionlist, str):
            sessionlist = [sessionlist, ]
        tmpvislist = inputs.vis
        if isinstance(tmpvislist, str):
            tmpvislist = [tmpvislist, ]
        vislist = []
        for vis in tmpvislist:
            if os.path.dirname(vis) == '':
                vislist.append(os.path.join(inputs.rawdata_dir, vis))
            else:
                vislist.append(vis)

        # Download ASDMs from the archive or products_dir to rawdata_dir.
        #   TBD: Currently assumed done somehow
        # Copy the required calibration products from someplace on disK
        #   default ../products to ../rawdata
        if inputs.copytoraw:
            self._do_copy_manifest_toraw('*pipeline_manifest.xml')
            pipemanifest = self._do_get_manifest('*pipeline_manifest.xml', '*cal*pipeline_manifest.xml')
            self._do_copytoraw(pipemanifest)
        else:
            pipemanifest = self._do_get_manifest('*pipeline_manifest.xml', '*cal*pipeline_manifest.xml')

        # Retrieve smoothing and spectral line spws information from the manifest
        spws_to_smooth = None  # If not found in the manifest, assume old data.
        specline_spws = 'none'
        params = None
        ms_name = "{}.ms".format(os.path.basename(vislist[0]))
        for asdm in pipemanifest.get_ous().findall(f".//asdm[@name=\'{ms_name}\']"):
            params = getattr(asdm.find('restoredata'), 'attrib', None)
        if params:
            spws_to_smooth = params.get('smoothed_spws', None)
            specline_spws = params.get('specline_spws', 'none')

            LOG.debug("Found smoothed_spws: {} and specline_spws: {} in the manifest".format(spws_to_smooth, specline_spws))
        else:
            LOG.debug("Didn't find smoothed_spws, specline_spws in the manifest.")

        # If there was an empty string, indicating no specline spws, in the manifest,
        # set the specline_spws to 'none' for hifv_importdata.
        if len(specline_spws) == 0:
            specline_spws = 'none'

        # Convert ASDMS assumed to be on disk in rawdata_dir. After this step
        # has been completed the MS and MS.flagversions directories will exist
        # and MS,flagversions will contain a copy of the original MS flags,
        # Flags.Original.
        #    TBD: Add error handling
        import_results = self._do_importasdm(sessionlist=sessionlist, vislist=vislist, specline_spws=specline_spws)

        spws_to_smooth_list = conversion.range_to_list(spws_to_smooth) if spws_to_smooth is not None else []

        _MSTOOLS_HANNING_CUTOFF = parse('2026.1.1.3')
        pipeline_version_original = None  # computed lazily on first need, then cached
        partial_mstools_hanning_mses = []
        for ms in self.inputs.context.observing_run.measurement_sets:
            spws = ms.get_spectral_windows(science_windows_only=True)
            partial_mstools_hanning = False
            if 0 < len(spws_to_smooth_list) < len(spws):
                # In older pipeline versions (2024.1.22–2025.1.0.37, after PIPE-672, before PIPE-2473,
                # i.e. ver<2026.1.1.3), partial Hanning smoothing (subset of SPWs) was done via mstools,
                # which is now deprecated.  Here we re-smooth using the Hanning task (mstransform-based) instead,
                # which might produce a different row order — so the extracted flagversions must be remapped.
                if pipeline_version_original is None:
                    # we delay the pipeline version check until we know it's needed, since it
                    # requires parsing the manifest and extracting the version string, which
                    # might not work for older manifests
                    _, pipeline_version, _ = self._extract_casa_pipeline_version(pipemanifest)
                    pipeline_version_original = parse(pipeline_version)
                if pipeline_version_original < _MSTOOLS_HANNING_CUTOFF:
                    partial_mstools_hanning = True
                    LOG.info(
                        'MS %s: original pipeline version %s used mstools (deprecated) for partial'
                        ' Hanning smoothing; re-smoothing via the Hanning task (mstransform-based)'
                        ' and remapping flagversions to the new row order',
                        ms.name,
                        pipeline_version_original,
                    )

            if partial_mstools_hanning:
                self._do_hanningsmooth(spws_to_smooth=spws_to_smooth, keep_original=True)
                partial_mstools_hanning_mses.append(ms)
            else:
                self._do_hanningsmooth(spws_to_smooth=spws_to_smooth)

        # Restore final MS.flagversions and flags (extracts production flagversions from tgz);
        # for MSes that required partial mstools Hanning, remaps flagversions to the new row order before restoring.
        self._do_restore_flags(pipemanifest, partial_mstools_hanning_mses=partial_mstools_hanning_mses)

        # Get the session list and the visibility files associated with
        # each session.
        session_names, session_vislists = self._get_sessions()

        # Restore calibration tables
        self._do_restore_caltables(pipemanifest, session_names=session_names, session_vislists=session_vislists)

        # Import calibration apply lists
        self._do_restore_calstate(pipemanifest)

        # Apply the calibrations.
        apply_results = self._do_applycal()

        # Return the results object, which will be used for the weblog
        return restoredata.RestoreDataResults(import_results, apply_results)

    # Override generic method and use an ALMA specific one. Not much difference
    # now but should simplify parameters in future
    def _do_importasdm(self, sessionlist, vislist, specline_spws):
        inputs = self.inputs
        container = vdp.InputsContainer(
            importdata.VLAImportData, inputs.context,
            vis=vislist, session=sessionlist, save_flagonline=False,
            lazy=inputs.lazy, bdfflags=inputs.bdfflags,
            asis=inputs.asis, ocorr_mode=inputs.ocorr_mode,
            specline_spws=specline_spws)
        importdata_task = importdata.VLAImportData(container)
        return self._executor.execute(importdata_task, merge=True)

    def _do_restore_flags(self, pipemanifest, flag_version_name=None, partial_mstools_hanning_mses=None):
        if flag_version_name is None:
            try_flag_version_names = ['statwt_1', 'Pipeline_Final']
        else:
            try_flag_version_names = [flag_version_name]
        inputs = self.inputs
        if pipemanifest is not None:
            ouss = pipemanifest.get_ous()
        else:
            ouss = None

        # Loop over MS list in working directory
        for ms in inputs.context.observing_run.measurement_sets:

            # Remove imported MS.flagversions from working directory
            flagversion = ms.basename + '.flagversions'
            flagversionpath = os.path.join(inputs.output_dir, flagversion)
            if os.path.exists(flagversionpath):
                LOG.info('Removing default flagversion for %s' % ms.basename)
                shutil.rmtree(flagversionpath)

            # Untar MS.flagversions file in rawdata_dir to output_dir
            if ouss is not None:
                tarfilename = os.path.join(inputs.rawdata_dir,
                                           pipemanifest.get_final_flagversions(ouss)[ms.basename])
            else:
                tarfilename = os.path.join(inputs.rawdata_dir,
                                           ms.basename + '.flagversions.tgz')
            LOG.info('Extracting %s' % flagversion)
            LOG.info('    From %s' % tarfilename)
            LOG.info('    Into %s' % inputs.output_dir)
            with tarfile.open(tarfilename, 'r:gz') as tar:
                tar.extractall(path=inputs.output_dir, filter='fully_trusted')

            # The original pipeline used the deprecated mstools for partial Hanning smoothing, but we
            # re-smooth via the Hanning task (mstransform-based), which produces a different row order.
            # Rename the extracted flagversions to pair with the preserved .original MS, then remap
            # them to match the new row order of the Hanning-smoothed MS.
            ms_path = os.path.join(inputs.output_dir, ms.basename)
            needs_remap = bool(partial_mstools_hanning_mses and ms in partial_mstools_hanning_mses)
            if needs_remap:
                original_flagversions_path = ms_path + '.original.flagversions'
                LOG.info("Renaming %s -> %s", flagversionpath, original_flagversions_path)
                os.rename(flagversionpath, original_flagversions_path)
                LOG.info("Remapping flagversions from %s.original to %s", ms_path, ms_path)
                utils.transfer_flagversion(ms_path + '.original', ms_path, remap_ids=False)

            # Restore final flags version using flagmanager
            try_version = None
            for flagname in try_flag_version_names:
                if os.path.exists(os.path.join(flagversionpath, 'flags.{}'.format(flagname))):
                    try_version = flagname
                    break
            LOG.info('Restoring final flags for %s from flag version %s' % (ms.basename, try_version))
            task = casa_tasks.flagmanager(vis=ms.name,
                                          mode='restore',
                                          versionname=try_version)
            try:
                self._executor.execute(task)
            except Exception:
                LOG.error("Application of final flags failed for %s" % ms.basename)
                raise

            # Clean up the .original MS and its flagversions now that flags have
            # been successfully restored into the Hanning-smoothed MS.
            if needs_remap:
                for path in (ms_path + '.original', ms_path + '.original.flagversions'):
                    if os.path.exists(path):
                        LOG.info("Removing %s", path)
                        shutil.rmtree(path)

    def _do_hanningsmooth(self, spws_to_smooth, keep_original=False):
        container = vdp.InputsContainer(hanning.Hanning, self.inputs.context,
                                        spws_to_smooth=spws_to_smooth,
                                        keep_original=keep_original)
        hanning_task = hanning.Hanning(container)
        return self._executor.execute(hanning_task, merge=True)

    def _do_applycal(self):

        flagsum = True
        flagdetailedsum = True
        if self.inputs.gainmap:
            flagsum = False
            flagdetailedsum = False

        container = vdp.InputsContainer(applycals.Applycals, self.inputs.context, intent='',
                                        field='', spw='', gainmap=self.inputs.gainmap,
                                        flagsum=flagsum, flagdetailedsum=flagdetailedsum)
        applycal_task = applycals.Applycals(container)
        return self._executor.execute(applycal_task, merge=True)

    def _convert_calstate_paths(self, applyfile: str) -> str:
        """Convert paths in the exported calstate to point to the new output directory.

        Args:
            applyfile: The path to the exported calstate file.

        Returns:
            The content of the file as a string.
        """
        # search-and-replace directory names in the exported calstate file
        with open(applyfile, 'r', encoding='utf-8') as f:
            return utils.convert_paths_to_basenames(f.read())
