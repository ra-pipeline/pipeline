import os
import shutil
import collections
import tarfile

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.vdp as vdp
from pipeline.h.tasks.exportdata import exportdata
from pipeline.infrastructure import task_registry
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.filenamer import fitsname
from . import vlaifaqua

LOG = infrastructure.get_logger(__name__)


class VLAExportDataInputs(exportdata.ExportDataInputs):
    gainmap = vdp.VisDependentProperty(default=False)
    exportcalprods = vdp.VisDependentProperty(default=False)
    imaging_products_only = vdp.VisDependentProperty(default=False)
    tarms = vdp.VisDependentProperty(default=True)

    @exportcalprods.postprocess
    def exportcalprods(self, value):
        # calibration products are exported when
        # (1) not imaging_product_only and not exportmses
        # OR
        # (2) not imaging_product_only and both exportmses and exportcalprods are True
        if self.imaging_products_only: return False
        elif not self.exportmses: return True
        else: return value

    def __init__(self, context, output_dir=None, session=None, vis=None, exportmses=None,
                 tarms=None, exportcalprods=None,
                 pprfile=None, calintents=None, calimages=None, targetimages=None, products_dir=None, gainmap=None,
                 imaging_products_only=None):
        super(VLAExportDataInputs, self).__init__(context, output_dir=output_dir, session=session, vis=vis,
                                                  exportmses=exportmses, pprfile=pprfile, calintents=calintents,
                                                  calimages=calimages, targetimages=targetimages,
                                                  products_dir=products_dir, imaging_products_only=imaging_products_only)
        self.gainmap = gainmap
        self.exportcalprods = exportcalprods
        self.tarms = tarms


@task_registry.set_equivalent_casa_task('hifv_exportdata')
class VLAExportData(exportdata.ExportData):

    # link the accompanying inputs to this task
    Inputs = VLAExportDataInputs

    def prepare(self):
        results = super().prepare()

        # PIPE-1205
        PbcorFits = collections.namedtuple('PbcorFits', 'pbcorimage pbcorfits nonpbcor_fits')
        # results.targetimages[0] is the same as self.inputs.context.sciimlist.get_imlist()

        # for each target in the targetimages results
        for target in results.targetimages[0]:
            fitsqueue = []
            if target['multiterm']:
                for nt in range(target['multiterm']):
                    pbcorimage = target['imagename'] + f'.pbcor.tt{nt}'
                    non_pbcorimage = target['imagename'] + f'.tt{nt}'
                    fitsfile = fitsname(self.inputs.products_dir, pbcorimage)
                    nonpbcor_fits = fitsname(self.inputs.products_dir, non_pbcorimage)
                    if os.path.exists(pbcorimage) and fitsfile not in target['fitsfiles']:
                        fitsqueue.append(PbcorFits(pbcorimage, fitsfile, nonpbcor_fits))
            else:
                pbcorimage = target['imagename'] + '.pbcor'
                fitsfile = fitsname(self.inputs.products_dir, pbcorimage)
                nonpbcor_fits = fitsname(self.inputs.products_dir, target['imagename'])
                if os.path.exists(pbcorimage) and fitsfile not in target['fitsfiles']:
                    fitsqueue.append(PbcorFits(pbcorimage, fitsfile, nonpbcor_fits))

            for ee in fitsqueue:
                # make the pbcor FITS images
                self._shorten_spwlist(ee.pbcorimage)
                task = casa_tasks.exportfits(imagename=ee.pbcorimage, fitsimage=ee.pbcorfits, velocity=False, optical=False,
                                        bitpix=-32, minpix=0, maxpix=-1, overwrite=True, dropstokes=False,
                                        stokeslast=True)
                self._executor.execute(task)

                # add new pbcor fits to 'fitsfiles'
                target['fitsfiles'].append(ee.pbcorfits)
                # add new pbcor fits to fitslist
                results.targetimages[1].append(ee.pbcorfits)

                # if there's a non-pbcor image in 'fitsfiles' move it to 'auxfitsfiles'
                if ee.nonpbcor_fits in target['fitsfiles']:
                    target['auxfitsfiles'].append(ee.nonpbcor_fits)
                    target['fitsfiles'].remove(ee.nonpbcor_fits)

        oussid = self.inputs.context.get_oussid()  # returns string of 'unknown' for VLA

        # Make the imaging vislist and the sessions lists.
        #     Force this regardless of the value of imaging_only_products
        session_list, session_names, session_vislists, vislist = super()._make_lists(
            self.inputs.context, self.inputs.session, self.inputs.vis, imaging_only_mses=False)

        # Export the auxiliary file products into a single tar file
        #    These are optional for reprocessing but informative to the user
        #    The calibrator source fluxes file
        #    The antenna positions file
        #    The continuum regions file
        #    The target flagging file
        recipe_name = self.get_recipename(self.inputs.context)
        if not recipe_name:
            prefix = oussid
        else:
            prefix = oussid + '.' + recipe_name
        auxfproducts = self._do_if_auxiliary_products(prefix, self.inputs.output_dir, self.inputs.products_dir, vislist,
                                                   self.inputs.imaging_products_only)

        # Export the AQUA report
        pipe_aqua_reportfile = self._export_aqua_report(context=self.inputs.context,
                                                        oussid=prefix,
                                                        products_dir=self.inputs.products_dir,
                                                        report_generator=vlaifaqua.VLAAquaXmlGenerator(),
                                                        weblog_filename=results.weblog)

        # Update the manifest
        if auxfproducts is not None or pipe_aqua_reportfile is not None:
            manifest_file = os.path.join(self.inputs.products_dir, results.manifest)
            self._add_to_manifest(manifest_file, auxfproducts, False, [], pipe_aqua_reportfile, oussid)

        return results

    def _shorten_spwlist(self, image):
        # PIPE-325: abbreviate 'spw' and/or 'virtspw' for FITS header when spw string is "too long"
        # TODO: elevate this function to h exportdata after the PL2021 release so that it can be used
        #   here as well as in h_exportdata.  Too close to a release candidate at the moment to disrupt
        #   ALMA validation.
        with casa_tools.ImageReader(image) as img:
            info = img.miscinfo()
            if 'spw' in info:
                if len(info['spw']) >= 68:
                    spw_sorted = sorted([int(x) for x in info['spw'].split(',')])
                    info['spw'] = '{},...,{}'.format(spw_sorted[0], spw_sorted[-1])
                    img.setmiscinfo(info)
            if 'virtspw' in info:
                if len(info['virtspw']) >= 68:
                    spw_sorted = sorted([int(x) for x in info['virtspw'].split(',')])
                    info['virtspw'] = '{},...,{}'.format(spw_sorted[0], spw_sorted[-1])
                    img.setmiscinfo(info)

    def _export_casa_restore_script(self, context, script_name, products_dir, oussid, vislist, session_list):
        """
        Save the CASA restore script.
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

        # VLA ocorr_value
        ocorr_mode = 'co'

        for vis in vislist:
            filename = os.path.basename(vis)
            if filename.endswith('.ms'):
                filename, filext = os.path.splitext(filename)
            tmpvislist.append(filename)
        task_string = "    hifv_restoredata (vis=%s, session=%s, ocorr_mode='%s', gainmap=%s)" % (
        tmpvislist, session_list, ocorr_mode, self.inputs.gainmap)

        # Is this a VLASS execution?
        vlassmode = False
        for result in context.results:
            try:
                resultinputs = result.read()[0].inputs
                if 'vlass' in resultinputs['checkflagmode']:
                    vlassmode = True
            except:
                continue

        if vlassmode:
            task_string += "\n    hifv_fixpointing()"

        task_string += "\n    hifv_statwt()"

        template = '''h_init()
try:
%s
finally:
    h_save()
''' % task_string

        with open(script_file, 'w') as casa_restore_file:
            casa_restore_file.write(template)

        LOG.info('Copying casa restore script %s to %s', script_file, out_script_file)
        shutil.copy(script_file, out_script_file)

        return os.path.basename(out_script_file)

    def _export_final_ms(self, context, vis, products_dir):
        """
        If kwarg exportmses is True then...
            If tarms is True (default):  Save the ms to a compressed tarfile in products directory
            Else copy the ms directly to the products directory.
        """
        # Define the name of the output tarfile
        visname = os.path.basename(vis)

        if self.inputs.tarms:

            tarfilename = visname + '.tgz'
            LOG.info('Storing final ms %s in %s', visname, tarfilename)

            # Create the tar file
            tar = tarfile.open(os.path.join(products_dir, tarfilename), "w:gz")
            tar.add(visname)
            tar.close()

            return tarfilename
        else:
            LOG.info('Copying final ms %s to %s', visname, os.path.join(products_dir, visname))
            shutil.copytree(visname, os.path.join(products_dir, visname))

            return visname
