from __future__ import annotations

import collections
import os
import shutil
import traceback
from typing import TYPE_CHECKING

from pipeline import infrastructure
from pipeline.h.tasks.exportdata import exportdata
from pipeline.infrastructure import task_registry, vdp

from . import almaifaqua

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)

AuxFileProducts = collections.namedtuple('AuxFileProducts', 'flux_file antenna_file cont_file flagtargets_list')


class ALMAExportDataInputs(exportdata.ExportDataInputs):

    imaging_products_only = vdp.VisDependentProperty(default=False)

    # docstring and type hints: supplements hifa_exportdata
    def __init__(
            self,
            context: Context,
            output_dir: str = None,
            session: list[str] = None,
            vis: list[str] = None,
            exportmses: bool = None,
            tarms: bool = None,
            pprfile: list[str] = None,
            calintents: str = None,
            calimages: list[str] = None,
            targetimages: list[str] = None,
            products_dir: str = None,
            imaging_products_only: bool = None,
            ):
        """Initialize the Inputs.

        Args:
            context: the pipeline Context state object

            output_dir: the working directory for pipeline data

            session: List of sessions one per visibility file. Currently defaults
                to a single virtual session containing all the visibility files in vis.
                In the future, this will default to the set of observing sessions defined
                in the context.
                Example: ``session=['session1', 'session2']``

            vis: List of visibility data files for which flagging and calibration
                information will be exported. Defaults to the list maintained in the
                pipeline context.
                Example: ``vis=['X227.ms', 'X228.ms']``

            exportmses: Export the final MeasurementSets instead of the final flags,
                calibration tables, and calibration instructions.

            tarms: Tar final MeasurementSets

            pprfile: Name of the pipeline processing request to be exported. Defaults
                to a file matching the template 'PPR_*.xml'.
                Example: ``pprfile=['PPR_GRB021004.xml']``

            calintents: List of calibrator image types to be exported. Defaults to
                all standard calibrator intents, ``'BANDPASS'``, ``'PHASE'``, ``'FLUX'``.
                Example: ``'PHASE'``

            calimages: List of calibrator images to be exported. Defaults to all
                calibrator images recorded in the pipeline context.
                Example: ``calimages=['3C454.3.bandpass', '3C279.phase']``

            targetimages: List of science target images to be exported. Defaults to all
                science target images recorded in the pipeline context.
                Example: ``targetimages=['NGC3256.band3', 'NGC3256.band6']``

            products_dir: Name of the data products subdirectory. Defaults to './'.
                Example: ``products_dir='../products'``

            imaging_products_only: Export science target imaging products only

        """
        super().__init__(context, output_dir=output_dir, session=session, vis=vis,
                         exportmses=exportmses, tarms=tarms, pprfile=pprfile, calintents=calintents,
                         calimages=calimages, targetimages=targetimages,
                         products_dir=products_dir,
                         imaging_products_only=imaging_products_only)


@task_registry.set_equivalent_casa_task('hifa_exportdata')
@task_registry.set_casa_commands_comment('The output data products are computed.')
class ALMAExportData(exportdata.ExportData):

    # link the accompanying inputs to this task
    Inputs = ALMAExportDataInputs

    def prepare(self):

        results = super().prepare()

        oussid = self.inputs.context.get_oussid()

        # Make the imaging vislist and the sessions lists.
        #     Force this regardless of the value of imaging_only_products
        _, session_names, session_vislists, vislist = super()._make_lists(
            self.inputs.context, self.inputs.session, self.inputs.vis, imaging_only_mses=True)

        # Depends on the existence of imaging mses
        if vislist:
            # Export the auxiliary caltables if any
            #    These are currently the uvcontinuum fit tables.
            auxcaltables = self._do_aux_session_products(self.inputs.context, oussid, session_names, session_vislists,
                                                         self.inputs.products_dir)

            # Export the auxiliary cal apply files if any
            #    These are currently the uvcontinuum fit tables.
            auxcalapplys = self._do_aux_ms_products(self.inputs.context, vislist, self.inputs.products_dir)
        else:
            auxcaltables = None
            auxcalapplys = None

        # Create and export the pipeline stats file
        pipeline_stats_file = None
        try:
            pipeline_stats_file = self._export_stats_file(context=self.inputs.context, oussid=oussid)
        except Exception as e:
            LOG.info("Unable to output pipeline statistics file: {}".format(e))
            LOG.debug(traceback.format_exc())
            pass

        # Export the auxiliary file products into a single tar file
        #    These are optional for reprocessing but informative to the user
        #    The calibrator source fluxes file
        #    The antenna positions file
        #    The continuum regions file
        #    The target flagging file
        #    The pipeline statistics file (if it exists)
        recipe_name = self.get_recipename(self.inputs.context)
        if not recipe_name:
            prefix = oussid
        else:
            prefix = oussid + '.' + recipe_name
        auxfproducts = self._do_if_auxiliary_products(prefix, self.inputs.output_dir, self.inputs.products_dir, vislist,
                                                   self.inputs.imaging_products_only, pipeline_stats_file)

        # Export the AQUA report
        pipe_aqua_reportfile = self._export_aqua_report(context=self.inputs.context,
                                                        oussid=prefix,
                                                        products_dir=self.inputs.products_dir,
                                                        report_generator=almaifaqua.AlmaAquaXmlGenerator(),
                                                        weblog_filename=results.weblog)

        # Update the manifest
        if auxfproducts is not None or pipe_aqua_reportfile is not None:
            manifest_file = os.path.join(self.inputs.products_dir, results.manifest)
            recipe_name = self.inputs.context.project_structure.recipe_name
            self._add_to_manifest(manifest_file, auxfproducts, auxcaltables, auxcalapplys, pipe_aqua_reportfile, oussid, recipe_name)

        return results

    def _do_aux_session_products(self, context, oussid, session_names, session_vislists, products_dir):

        # Make the standard sessions dictionary and export per session products
        #    Currently these are compressed tar files of per session calibration tables
        sessiondict = super()._do_standard_session_products(
            context, oussid, session_names, session_vislists, products_dir, imaging=True)

        return sessiondict

    def _do_aux_ms_products(self, context, vislist, products_dir):

        # Loop over the measurements sets in the working directory, and
        # create the calibration apply file(s) in the products directory.
        apply_file_list = []
        for visfile in vislist:
            apply_file = super()._export_final_applylist(
                context, visfile, products_dir, imaging=True)
            apply_file_list.append(apply_file)

        # Create the ordered vis dictionary
        #    The keys are the base vis names
        #    The values are a tuple containing the flags and applycal files
        visdict = collections.OrderedDict()
        for i in range(len(vislist)):
            visdict[os.path.basename(vislist[i])] = \
                os.path.basename(apply_file_list[i])

        return visdict

    def _export_casa_restore_script(self, context, script_name, products_dir, oussid, vislist, session_list):
        """
        Save the CASA restore scropt.
        """
        # Generate the file list

        # Get the output file name
        ps = context.project_structure
        script_file = os.path.join(context.report_dir, script_name)
        out_script_file = self.NameBuilder.casa_script(script_name,
                                                       project_structure=ps,
                                                       ousstatus_entity_id=oussid,
                                                       output_dir=products_dir)

        LOG.info('Creating casa restore script %s', script_file)

        # This is hardcoded.
        tmpvislist = []

        # ALMA default
        ocorr_mode = 'ca'

        for vis in vislist:
            filename = os.path.basename(vis)
            if filename.endswith('.ms'):
                filename, filext = os.path.splitext(filename)
            tmpvislist.append(filename)
        task_string = "    hifa_restoredata (vis=%s, session=%s, ocorr_mode='%s')" % (tmpvislist, session_list,
                                                                                      ocorr_mode)

        template = '''h_init()
try:
%s
finally:
    h_save()
''' % task_string

        with open(script_file, 'w') as casa_restore_file:
            casa_restore_file.write(template)

        LOG.info('Copying casa restore script %s to %s' % (script_file, out_script_file))
        shutil.copy(script_file, out_script_file)

        return os.path.basename(out_script_file)
