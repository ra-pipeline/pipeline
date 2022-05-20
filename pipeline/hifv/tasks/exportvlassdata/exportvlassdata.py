import collections
import errno
import fnmatch
import os
import shutil
import tarfile
import re
import astropy.io.fits as apfits

import pipeline as pipeline
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline import environment
from pipeline.h.tasks.common import manifest
from pipeline.h.tasks.exportdata import exportdata
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry
from pipeline.infrastructure import utils
from pipeline.domain import DataType

LOG = infrastructure.get_logger(__name__)

StdFileProducts = collections.namedtuple('StdFileProducts', 'ppr_file weblog_file casa_commands_file casa_pipescript parameterlist')

import re
import glob

def atoi(text):
    return int(text) if text.isdigit() else text


def natural_keys(text):
    """
    alist.sort(key=natural_keys) sorts in human order
    http://nedbatchelder.com/blog/200712/human_sorting.html
    (See Toothy's implementation in the comments)
    https://stackoverflow.com/questions/5967500/how-to-correctly-sort-a-string-with-a-number-inside
    """
    return [ atoi(c) for c in re.split(r'(\d+)', text) ]

class ExportvlassdataResults(basetask.Results):
    def __init__(self, final=[], pool=[], preceding=[]):
        super(ExportvlassdataResults, self).__init__()
        self.pool = pool[:]
        self.final = final[:]
        self.preceding = preceding[:]
        self.error = set()

    def __repr__(self):
        return 'ExportvlassdataResults:'


class ExportvlassdataInputs(exportdata.ExportDataInputs):
    gainmap = vdp.VisDependentProperty(default=False)

    def __init__(self, context, output_dir=None, session=None, vis=None, exportmses=None, pprfile=None, calintents=None,
                 calimages=None, targetimages=None, products_dir=None, gainmap=None):
        super(ExportvlassdataInputs, self).__init__(context, output_dir=output_dir, session=session, vis=vis,
                                                    exportmses=exportmses, pprfile=pprfile, calintents=calintents,
                                                    calimages=calimages, targetimages=targetimages,
                                                    products_dir=products_dir)
        self.gainmap = gainmap


@task_registry.set_equivalent_casa_task('hifv_exportvlassdata')
class Exportvlassdata(basetask.StandardTaskTemplate):
    Inputs = ExportvlassdataInputs

    NameBuilder = exportdata.PipelineProductNameBuilder

    def prepare(self):

        LOG.info("This Exportvlassdata class is running.")

        # Create a local alias for inputs, so we're not saying
        # 'self.inputs' everywhere
        inputs = self.inputs

        try:
            LOG.trace('Creating products directory: {!s}'.format(inputs.products_dir))
            os.makedirs(inputs.products_dir)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                pass
            else:
                raise

        # Initialize the standard ous is string.
        oussid = self.get_oussid(inputs.context)

        # Define the results object
        result = ExportvlassdataResults()

        # Make the standard vislist and the sessions lists.
        session_list, session_names, session_vislists, vislist = self._make_lists(inputs.context, inputs.session,
                                                                                  inputs.vis)

        # Export the standard per OUS file products
        #    The pipeline processing request
        #    A compressed tarfile of the weblog
        #    The pipeline processing script
        #    The CASA commands log
        recipe_name = self.get_recipename(inputs.context)
        if not recipe_name:
            prefix = oussid
        else:
            prefix = oussid + '.' + recipe_name
        stdfproducts = self._do_standard_ous_products(inputs.context, prefix, inputs.pprfile, inputs.output_dir,
                                                      inputs.products_dir)
        if stdfproducts.ppr_file:
            result.pprequest = os.path.basename(stdfproducts.ppr_file)
        result.weblog = os.path.basename(stdfproducts.weblog_file)
        result.pipescript = os.path.basename(stdfproducts.casa_pipescript)
        result.commandslog = os.path.basename(stdfproducts.casa_commands_file)
        if stdfproducts.parameterlist:
            result.parameterlist = os.path.basename(stdfproducts.parameterlist)

        imlist = self.inputs.context.subimlist.get_imlist()

        # PIPE-592: find out imaging mode (stored in context by hif_editimlist)
        if hasattr(self.inputs.context, 'imaging_mode'):
            img_mode = self.inputs.context.imaging_mode
        else:
            LOG.warning("imaging_mode property does not exist in context, alpha images will not be written.")
            img_mode = None

        images_list = []
        for imageitem in imlist:

            if imageitem['multiterm']:
                pbcor_image_name = imageitem['imagename'].replace('subim', 'pbcor.tt0.subim')
                rms_image_name = imageitem['imagename'].replace('subim', 'pbcor.tt0.rms.subim')
                image_bundle = [pbcor_image_name, rms_image_name]
                # PIPE-592: save VLASS SE alpha and alpha error images
                if type(img_mode) is str and img_mode.startswith('VLASS-SE-CONT'):
                    alpha_image_name = imageitem['imagename'].replace('.image.subim', '.alpha.subim')
                    alpha_image_error_name = imageitem['imagename'].replace('.image.subim', '.alpha.error.subim')
                    image_bundle.extend([alpha_image_name, alpha_image_error_name])

                    # PIPE-1038:  Adding new export products
                    pbcor_image_name = imageitem['imagename'].replace('subim', 'pbcor.tt1.subim')
                    rms_image_name = imageitem['imagename'].replace('subim', 'pbcor.tt1.rms.subim')
                    image_bundle.extend([pbcor_image_name, rms_image_name])

                    # No FITS file created
                    tt0_initial_models = glob.glob('*iter1.model.tt0*')
                    tt0_initial_models.sort(key=natural_keys)
                    tt0_initial_model_name = tt0_initial_models[0]
                    # tt0_initial_model_name = imageitem['imagename'].replace('iter3.image.subim', 'iter1.model.tt0')
                    # tt0_initial_model_name = tt0_initial_model_name.replace('s13', 's5')

                    tt1_initial_models = glob.glob('*iter1.model.tt1*')
                    tt1_initial_models.sort(key=natural_keys)
                    tt1_initial_model_name = tt1_initial_models[0]
                    # tt1_initial_model_name = imageitem['imagename'].replace('iter3.image.subim', 'iter1.model.tt1')
                    # tt1_initial_model_name = tt1_initial_model_name.replace('s13', 's5')

                    # Create list for tar file
                    self.initial_models = [tt0_initial_model_name, tt1_initial_model_name]

                    # No FITS files created
                    tt0_final_model_name = imageitem['imagename'].replace('image.subim', 'model.tt0')
                    tt1_final_model_name = imageitem['imagename'].replace('image.subim', 'model.tt1')

                    # Create list for tar file
                    self.final_models = [tt0_final_model_name, tt1_final_model_name]

            else:
                pbcor_image_name = imageitem['imagename'].replace('subim', 'pbcor.subim')
                rms_image_name = imageitem['imagename'].replace('subim', 'pbcor.rms.subim')
                image_bundle = [pbcor_image_name, rms_image_name]
            images_list.extend(image_bundle)

        # Add masks for PIPE-1038
        self.masks = []
        if type(img_mode) is str and img_mode.startswith('VLASS-SE-CONT'):
            QLmasks = glob.glob('*.QLcatmask-tier1.mask')
            QLmasks.sort(key=natural_keys)
            QLmask = QLmasks[-1]
            secondmasks = glob.glob('*.secondmask.mask')
            secondmasks.sort(key=natural_keys)
            secondmask = secondmasks[-1]
            finalmasks = glob.glob('*.combined-tier2.mask')
            finalmasks.sort(key=natural_keys)
            finalmask = finalmasks[-1]

            # Create list for tar file
            self.masks = [QLmask, secondmask, finalmask]


        fits_list = []
        for image in images_list:
            fitsfile = os.path.join(inputs.products_dir, image + '.fits')

            # PIPE-1182: Strip stage number off exported image fits files
            #   Look for "sX_Y.", where X and Y are one or more digits at the start of the image name
            pattern = r'^s\d+_\d*\.'
            mm = re.search(pattern, image)
            if mm:
                LOG.info(f'Removing "{mm.group()}" from "{image}" before exporting to FITS.')
                fitsfile = fitsfile.replace(mm.group(), '')

            task = casa_tasks.exportfits(imagename=image, fitsimage=fitsfile)

            self._executor.execute(task)
            LOG.info('Wrote {ff}'.format(ff=fitsfile))
            fits_list.append(fitsfile)

            # Apply position corrections to VLASS QL, MOSAIC and AWP=1 product images (PIPE-587, PIPE-641, PIPE-1134)
            if img_mode in ('VLASS-QL', 'VLASS-SE-CONT-MOSAIC', 'VLASS-SE-CONT-AWP-P001'):
                # Mean antenna geographic coordinates
                observatory = casa_tools.measures.observatory(self.inputs.context.project_summary.telescope)
                # Mean observing date
                start_time = self.inputs.context.observing_run.start_datetime
                end_time = self.inputs.context.observing_run.end_datetime
                mid_time = start_time + (end_time - start_time) / 2
                mid_time = casa_tools.measures.epoch('utc', mid_time.isoformat())
                # Correction
                utils.positioncorrection.do_wide_field_pos_cor(fitsfile, date_time=mid_time, obs_long=observatory['m0'],
                                                               obs_lat=observatory['m1'])
                # Update FITS header
                self._fix_vlass_fits_header(self.inputs.context, fitsfile, img_mode)

        # Export the pipeline manifest file
        #    TBD Remove support for auxiliary data products to the individual pipelines
        pipemanifest = self._make_pipe_manifest(inputs.context, oussid, stdfproducts, {}, {}, [], fits_list)
        casa_pipe_manifest = self._export_pipe_manifest('pipeline_manifest.xml', inputs.products_dir, pipemanifest)
        result.manifest = os.path.basename(casa_pipe_manifest)

        # SE Cont imaging mode export for VLASS
        if type(img_mode) is str and img_mode.startswith('VLASS-SE-CONT'):
            # Export tar file
            reimaging_resources_tarfile = self._export_reimaging_resources(inputs.context, inputs.products_dir, oussid)

        # Return the results object, which will be used for the weblog
        return result

    def analyse(self, results):
        return results

    def get_oussid(self, context):
        """
        Determine the ous prefix
        """

        # Get the parent ous ousstatus name. This is the sanitized ous
        # status uid
        ps = context.project_structure
        if ps is None:
            oussid = 'unknown'
        elif ps.ousstatus_entity_id == 'unknown':
            oussid = 'unknown'
        else:
            oussid = ps.ousstatus_entity_id.translate(str.maketrans(':/', '__'))

        return oussid

    def get_recipename(self, context):
        """
        Get the recipe name
        """

        # Get the parent ous ousstatus name. This is the sanitized ous
        # status uid
        ps = context.project_structure
        if ps is None:
            recipe_name = ''
        elif ps.recipe_name == 'Undefined':
            recipe_name = ''
        else:
            recipe_name = ps.recipe_name

        return recipe_name

    def _has_imaging_data(self, context, vis):
        """
        Check if the given vis contains any imaging data.
        """

        imaging_datatypes = [DataType.SELFCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE, DataType.SELFCAL_LINE_SCIENCE, DataType.REGCAL_LINE_SCIENCE]
        ms_object = context.observing_run.get_ms(name=vis)
        return any(ms_object.get_data_column(datatype) for datatype in imaging_datatypes)

    def _make_lists(self, context, session, vis, imaging=False):
        """
        Create the vis and sessions lists
        """

        # Force inputs.vis to be a list.
        vislist = vis
        if isinstance(vislist, str):
            vislist = [vislist, ]
        if imaging:
            vislist = [vis for vis in vislist if self._has_imaging_data(context, vis)]
        else:
            vislist = [vis for vis in vislist if not self._has_imaging_data(context, vis)]

        # Get the session list and the visibility files associated with
        # each session.
        session_list, session_names, session_vislists = self._get_sessions(context, session, vislist)

        return session_list, session_names, session_vislists, vislist

    def _do_standard_ous_products(self, context, oussid, pprfile, output_dir, products_dir):
        """
        Generate the per ous standard products
        """

        # Locate and copy the pipeline processing request.
        #     There should normally be at most one pipeline processing request.
        #     In interactive mode there is no PPR.
        ppr_files = self._export_pprfile(context, output_dir, products_dir, oussid, pprfile)
        if ppr_files != []:
            ppr_file = os.path.basename(ppr_files[0])
        else:
            ppr_file = None

        # Export a tar file of the web log
        weblog_file = self._export_weblog(context, products_dir, oussid)

        # Export the processing log independently of the web log
        casa_commands_file = self._export_casa_commands_log(context,
                                                            context.logs['casa_commands'], products_dir, oussid)

        # Export the processing script independently of the web log
        casa_pipescript = self._export_casa_script(context, context.logs['pipeline_script'], products_dir, oussid)

        # Export the parameter list independently of the weblog for both QL and SE Imaging recipes
        edit_result = context.results[1].read()
        if edit_result.inputs['parameter_file']:
            parameterlist_filename = edit_result.inputs['parameter_file']
            parameterlist = self._export_parameterlist(context, parameterlist_filename, products_dir, oussid)
        else:
            parameterlist = None

        if hasattr(self.inputs.context, 'imaging_mode'):
            img_mode = self.inputs.context.imaging_mode
        else:
            LOG.warning("imaging_mode property does not exist in context, SE Cont imaging products will not be exported")
            img_mode = None

        # SE Cont imaging mode export for VLASS
        if type(img_mode) is str and img_mode.startswith('VLASS-SE-CONT'):
            # Identify self cal table
            selfcal_result = None
            for result in context.results:
                try:
                    selfcal_result = result.read()[0]
                    if 'self-cal' in selfcal_result.caltable:
                        break
                except Exception as e:
                    continue

            if selfcal_result:
                self.selfcaltable = selfcal_result.caltable
            else:
                self.selfcaltable = ''
                LOG.warning('Unable to locate self-cal table.')

            # Identify flagversion
            self.flagversion = os.path.basename(self.inputs.vis)+'.flagversions'

        return StdFileProducts(ppr_file,
                               weblog_file,
                               casa_commands_file,
                               casa_pipescript,
                               parameterlist)

    def _make_pipe_manifest(self, context, oussid, stdfproducts, sessiondict, visdict, calimages, targetimages):
        """
        Generate the manifest file
        """

        # Initialize the manifest document and the top level ous status.
        pipemanifest = self._init_pipemanifest(oussid)
        ouss = pipemanifest.set_ous(oussid)
        pipemanifest.add_casa_version(ouss, environment.casa_version_string)
        pipemanifest.add_pipeline_version(ouss, pipeline.revision)
        pipemanifest.add_procedure_name(ouss, context.project_structure.recipe_name)

        if stdfproducts.ppr_file:
            pipemanifest.add_pprfile(ouss, os.path.basename(stdfproducts.ppr_file))

        # Add the flagging and calibration products
        for session_name in sessiondict:
            session = pipemanifest.set_session(ouss, session_name)
            pipemanifest.add_caltables(session, sessiondict[session_name][1])
            for vis_name in sessiondict[session_name][0]:
                pipemanifest.add_asdm(session, vis_name, visdict[vis_name][0], visdict[vis_name][1])

        # Add a tar file of the web log
        pipemanifest.add_weblog(ouss, os.path.basename(stdfproducts.weblog_file))

        # Add the processing log independently of the web log
        pipemanifest.add_casa_cmdlog(ouss, os.path.basename(stdfproducts.casa_commands_file))

        # Add the processing script independently of the web log
        pipemanifest.add_pipescript(ouss, os.path.basename(stdfproducts.casa_pipescript))

        # Add the calibrator images
        pipemanifest.add_images(ouss, calimages, 'calibrator')

        # Add the target images
        pipemanifest.add_images(ouss, targetimages, 'target')

        return pipemanifest

    def _init_pipemanifest(self, oussid):
        """
        Initialize the pipeline manifest
        """

        pipemanifest = manifest.PipelineManifest(oussid)
        return pipemanifest

    def _export_pprfile(self, context, output_dir, products_dir, oussid, pprfile):

        # Prepare the search template for the pipeline processing request file.
        #    Was a template in the past
        #    Forced to one file now but keep the template structure for the moment
        if pprfile == '':
            ps = context.project_structure
            if ps is None:
                pprtemplate = None
            elif ps.ppr_file == '':
                pprtemplate = None
            else:
                pprtemplate = os.path.basename(ps.ppr_file)
        else:
            pprtemplate = os.path.basename(pprfile)

        # Locate the pipeline processing request(s) and  generate a list
        # to be copied to the data products directory. Normally there
        # should be only one match but if there are more copy them all.
        pprmatches = []
        if pprtemplate is not None:
            for file in os.listdir(output_dir):
                if fnmatch.fnmatch(file, pprtemplate):
                    LOG.debug('Located pipeline processing request %s' % file)
                    pprmatches.append(os.path.join(output_dir, file))

        # Copy the pipeline processing request files.
        pprmatchesout = []
        for file in pprmatches:
            if oussid:
                outfile = os.path.join(products_dir, oussid + '.pprequest.xml')
            else:
                outfile = file
            pprmatchesout.append(outfile)
            LOG.info('Copying pipeline processing file %s to %s' % (os.path.basename(file), os.path.basename(outfile)))
            if not self._executor._dry_run:
                shutil.copy(file, outfile)

        return pprmatchesout

    def _get_sessions(self, context, sessions, vis):
        """
        Return a list of sessions where each element of the list contains
        the vis files associated with that session. In future this routine
        will be driven by the context but for now use the user defined sessions
        """

        # If the input session list is empty put all the visibility files
        # in the same session.
        if len(sessions) == 0:
            wksessions = []
            for visname in vis:
                session = context.observing_run.get_ms(name=visname).session
                wksessions.append(session)
        else:
            wksessions = sessions

        # Determine the number of unique sessions.
        session_seqno = 0
        session_dict = {}
        for i in range(len(wksessions)):
            if wksessions[i] not in session_dict:
                session_dict[wksessions[i]] = session_seqno
                session_seqno = session_seqno + 1

        # Initialize the output session names and visibility file lists
        session_names = []
        session_vis_list = []
        for key, value in sorted(session_dict.items(), key=lambda k_v: (k_v[1], k_v[0])):
            session_names.append(key)
            session_vis_list.append([])

        # Assign the visibility files to the correct session
        for j in range(len(vis)):
            # Match the session names if possible
            if j < len(wksessions):
                for i in range(len(session_names)):
                    if wksessions[j] == session_names[i]:
                        session_vis_list[i].append(vis[j])
            # Assign to the last session
            else:
                session_vis_list[len(session_names) - 1].append(vis[j])

        # Log the sessions
        for i in range(len(session_vis_list)):
            LOG.info('Visibility list for session %s is %s' % (session_names[i], session_vis_list[i]))

        return wksessions, session_names, session_vis_list

    def _export_weblog(self, context, products_dir, oussid):
        """
        Save the processing web log to a tarfile
        """

        # Save the current working directory and move to the pipeline
        # working directory. This is required for tarfile IO
        cwd = os.getcwd()
        os.chdir(os.path.abspath(context.output_dir))

        # Define the name of the output tarfile
        ps = context.project_structure
        tarfilename = self.NameBuilder.weblog(project_structure=ps,
                                              ousstatus_entity_id=oussid)
        # if ps is None:
        #     tarfilename = 'weblog.tgz'
        # elif ps.ousstatus_entity_id == 'unknown':
        #     tarfilename = 'weblog.tgz'
        # else:
        #     tarfilename = oussid + '.weblog.tgz'

        LOG.info('Saving final weblog in %s' % tarfilename)

        # Create the tar file
        if not self._executor._dry_run:
            tar = tarfile.open(os.path.join(products_dir, tarfilename), "w:gz")
            tar.add(os.path.join(os.path.basename(os.path.dirname(context.report_dir)), 'html'))
            tar.close()

        # Restore the original current working directory
        os.chdir(cwd)

        return tarfilename

    def _export_reimaging_resources(self, context, products_dir, oussid):
        """
        Tar up the reimaging resources for archiving (tarfile)
        """
        # Save the current working directory and move to the pipeline
        # working directory. This is required for tarfile IO
        cwd = os.getcwd()
        os.chdir(os.path.abspath(context.output_dir))

        # Define the name of the output tarfile
        ps = context.project_structure
        tarfilename = 'reimaging_resources.tgz'

        LOG.info('Saving reimaging resources in %s...' % tarfilename)

        # Create the tar file

        if not self._executor._dry_run:
            tar = tarfile.open(os.path.join(products_dir, tarfilename), "w:gz")

            for mask in self.masks:
                tar.add(mask, mask)
                LOG.info('....Adding {!s}'.format(mask))

            for initial_model in self.initial_models:
                tar.add(initial_model, initial_model)
                LOG.info('....Adding {!s}'.format(initial_model))

            for final_model in self.final_models:
                tar.add(final_model, final_model)
                LOG.info('....Adding {!s}'.format(final_model))

            tar.add(self.selfcaltable, self.selfcaltable)
            LOG.info('....Adding {!s}'.format(self.selfcaltable))

            tar.add(self.flagversion, self.flagversion)
            LOG.info('....Adding {!s}'.format(self.flagversion))
            tar.close()

        # Restore the original current working directory
        os.chdir(cwd)

        return tarfilename

    def _export_parameterlist(self, context, parameterlist_name, products_dir, oussid):
        """
        Save the parameter list
        """

        out_parameterlist_file = os.path.join(products_dir, os.path.basename(parameterlist_name))

        LOG.info('Copying parameter list file %s to %s' % (parameterlist_name, out_parameterlist_file))
        if not self._executor._dry_run:
            shutil.copy(parameterlist_name, out_parameterlist_file)

        return os.path.basename(out_parameterlist_file)

    def _export_table(self, context, table_name, products_dir, oussid):
        """
        Save directories (either cal table or flag versions)
        """

        ps = context.project_structure
        table_file = table_name
        out_table_file = os.path.join(products_dir, table_file)

        LOG.info('Copying product from %s to %s' % (table_file, out_table_file))
        if not self._executor._dry_run:
            shutil.copytree(table_file, out_table_file)

        return os.path.basename(out_table_file)

    def _export_casa_commands_log(self, context, casalog_name, products_dir, oussid):
        """
        Save the CASA commands file.
        """

        ps = context.project_structure
        casalog_file = os.path.join(context.report_dir, casalog_name)
        out_casalog_file = self.NameBuilder.casa_script(casalog_name,
                                                        project_structure=ps,
                                                        ousstatus_entity_id=oussid,
                                                        output_dir=products_dir)
        # if ps is None:
        #     casalog_file = os.path.join(context.report_dir, casalog_name)
        #     out_casalog_file = os.path.join(products_dir, casalog_name)
        # elif ps.ousstatus_entity_id == 'unknown':
        #     casalog_file = os.path.join(context.report_dir, casalog_name)
        #     out_casalog_file = os.path.join(products_dir, casalog_name)
        # else:
        #     casalog_file = os.path.join(context.report_dir, casalog_name)
        #     out_casalog_file = os.path.join(products_dir, oussid + '.' + casalog_name)

        LOG.info('Copying casa commands log %s to %s' % (casalog_file, out_casalog_file))
        if not self._executor._dry_run:
            shutil.copy(casalog_file, out_casalog_file)

        return os.path.basename(out_casalog_file)

    def _export_casa_script(self, context, casascript_name, products_dir, oussid):
        """
        Save the CASA script.
        """

        ps = context.project_structure
        casascript_file = os.path.join(context.report_dir, casascript_name)
        out_casascript_file = self.NameBuilder.casa_script(casascript_name,
                                                           project_structure=ps,
                                                           ousstatus_entity_id=oussid,
                                                           output_dir=products_dir)
        # if ps is None:
        #     casascript_file = os.path.join(context.report_dir, casascript_name)
        #     out_casascript_file = os.path.join(products_dir, casascript_name)
        # elif ps.ousstatus_entity_id == 'unknown':
        #     casascript_file = os.path.join(context.report_dir, casascript_name)
        #     out_casascript_file = os.path.join(products_dir, casascript_name)
        # else:
        #     # ousid = ps.ousstatus_entity_id.translate(str.maketrans(':/', '__'))
        #     casascript_file = os.path.join(context.report_dir, casascript_name)
        #     out_casascript_file = os.path.join(products_dir, oussid + '.' + casascript_name)

        LOG.info('Copying casa script file %s to %s' % (casascript_file, out_casascript_file))
        if not self._executor._dry_run:
            shutil.copy(casascript_file, out_casascript_file)

        return os.path.basename(out_casascript_file)

    def _export_pipe_manifest(self, manifest_name, products_dir, pipemanifest):
        """
        Save the manifest file.
        """

        out_manifest_file = os.path.join(products_dir, manifest_name)
        LOG.info('Creating manifest file %s' % out_manifest_file)
        if not self._executor._dry_run:
            pipemanifest.write(out_manifest_file)

        return out_manifest_file

    def _fix_vlass_fits_header(self, context, fitsname, img_mode):
        """
        Update VLASS FITS product header according to PIPE-641.
        Should be called in the following imaging modes:
            'VLASS-QL', 'VLASS-SE-CONT-MOSAIC', and 'VLASS-SE-CONT-AWP-P001'

        The following keywords are changed: DATE-OBS, DATE-END, RADESYS, OBJECT.
        """

        if os.path.exists(fitsname):
            # Open FITS image and obtain header
            hdulist = apfits.open(fitsname, mode='update')
            header = hdulist[0].header

            # DATE-OBS and DATE-END keywords
            # Note: the new DATE-OBS value (first scan start time) might differ from the original value
            # (first un-flagged scan start time).
            header['date-obs'] = (infrastructure.utils.get_epoch_as_datetime(
                context.observing_run.start_time).isoformat(), 'First scan started')
            date_end = ('date-end', infrastructure.utils.get_epoch_as_datetime(
                context.observing_run.end_time).isoformat(), 'Last scan finished')
            if 'date-end' in [k.lower() for k in header.keys()]:
                header['date-end'] = date_end[1:]
            else:
                pos = header.index('date-obs')
                header.insert(pos, date_end, after=True)

            # RADESYS
            if header['radesys'].upper() == 'FK5':
                header['radesys'] = 'ICRS'

            # OBJECT
            # We assume that the FITS name follows the convention described in PIPE-968 (minus the stage
            #    prefixes) and directly extract the 'OBJECT' name (first FIELD name of the image) from it.

            filename_components = os.path.basename(fitsname).split('.')
            object_name = ''
            object_name = filename_components[4]
            if object_name != '' and header['object'].upper() != object_name.upper():
                header['object'] = object_name

            # Save changes and inform log
            hdulist.flush()
            LOG.info("Header updated in {}".format(fitsname))

            # Close FITS file
            hdulist.close()

        else:
            LOG.warning('FITS header cannot be updated: image {} does not exist.'.format(fitsname))

        return
