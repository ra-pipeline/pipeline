import collections
import os
import shutil

import numpy

import pipeline.h.tasks.importdata.importdata as importdata
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.mpihelpers as mpihelpers
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.vdp as vdp
from pipeline.hifv.heuristics.vlascanheuristics import VLAScanHeuristics
from pipeline.hifv.heuristics.specline_detect import detect_spectral_lines
from pipeline.infrastructure import casa_tasks, casa_tools, task_registry

LOG = infrastructure.get_logger(__name__)


class VLAImportDataInputs(importdata.ImportDataInputs):
    # Override defaults in ImportDataInputs
    asis = vdp.VisDependentProperty(default='Receiver CalAtmosphere')
    ocorr_mode = vdp.VisDependentProperty(default='co')
    bdfflags = vdp.VisDependentProperty(default=False)
    process_caldevice = vdp.VisDependentProperty(default=True)
    createmms = vdp.VisDependentProperty(default='false')
    specline_spws = vdp.VisDependentProperty(default='auto')
    parallel = sessionutils.parallel_inputs_impl(default=False)

    # docstring and type hints: supplements hifv_importdata
    def __init__(self, context, vis=None, output_dir=None, asis=None, process_caldevice=None, session=None,
                 overwrite=None, nocopy=None, bdfflags=None, lazy=None, save_flagonline=None, createmms=None,
                 ocorr_mode=None, datacolumns=None, specline_spws=None, parallel=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context.

            vis: List of visibility data files. These may be ASDMs, tar files of ASDMs, MSes, or tar files of MSes, If ASDM files are specified, they will be
                converted  to MS format.

                Example: vis=['X227.ms', 'asdms.tar.gz']

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            asis: Creates verbatim copies of the ASDM tables in the output MS. The value given to this option must be a list of table names
                separated by space characters.
                examples:

                - asis='Receiver CalAtmosphere'
                - asis='Receiver', asis=''

            process_caldevice:

            session: List of sessions to which the visibility files belong. Defaults to a single session containing all the visibility files, otherwise
                a session must be assigned to each vis file.

                Example: session=['Session_1', 'Sessions_2']

            overwrite: Overwrite existing files on import.

            nocopy: When importing an MS, disable copying of the MS to the working directory.

            bdfflags:

            lazy:

            save_flagonline:

            createmms: Create a multi-MeasurementSet ('true') ready for parallel processing, or a standard MeasurementSet ('false'). The default setting
                ('automatic') creates an MMS if running in a cluster environment.

            ocorr_mode: Read in cross- and auto-correlation data(ca), cross- correlation data only (co), or autocorrelation data only (ao).

            datacolumns: Dictionary defining the data types of existing columns. The format is:

                {'data': 'data type 1'}

                or

                {'data': 'data type 1', 'corrected': 'data type 2'}

                For ASDMs the data type can only be RAW and one
                can only specify it for the data column.
                For MSes one can define two different data types
                for the DATA and CORRECTED_DATA columns and they
                can be any of the known data types (RAW,
                REGCAL_CONTLINE_ALL, REGCAL_CONTLINE_SCIENCE,
                SELFCAL_CONTLINE_SCIENCE, REGCAL_LINE_SCIENCE,
                SELFCAL_LINE_SCIENCE, BASELINED, ATMCORR). The
                intent selection strings _ALL or _SCIENCE can be
                skipped. In that case the task determines this
                automatically by inspecting the existing intents
                in the dataset.
                Usually, a single datacolumns dictionary is used
                for all datasets. If necessary, one can define a
                list of dictionaries, one for each EB, with
                different setups per EB.
                If no types are specified,
                {'data':'raw','corrected':'regcal_contline'}
                or {'data':'raw'} will be assumed, depending on
                whether the corrected column exists or not.

            specline_spws: String indicating how the pipeline should determine whether a spw should be processed as a spectral line window or continuum. The default setting of
                'auto' will use defined heuristics to determine this definition. Accepted
                values are 'auto', 'none' (no spws will be defined as spectral line), or
                a string of spw definitions in the CASA format.

                Example: specline_spws='2, 3, 4~9, 23'

            parallel: Execute using CASA HPC functionality, if available.

        """
        super().__init__(context, vis=vis, output_dir=output_dir, asis=asis,
                         process_caldevice=process_caldevice, session=session,
                         overwrite=overwrite, nocopy=nocopy, bdfflags=bdfflags, lazy=lazy,
                         save_flagonline=save_flagonline, createmms=createmms,
                         ocorr_mode=ocorr_mode, datacolumns=datacolumns)
        self.specline_spws = specline_spws
        self.parallel = parallel


class VLAImportDataResults(basetask.Results):
    def __init__(self, mses=None, setjy_results=None):
        super().__init__()

        if mses is None:
            mses = []
        self.mses = mses
        self.setjy_results = setjy_results
        self.origin = {}

    def merge_with_context(self, context):
        target = context.observing_run

        for ms in self.mses:
            LOG.info('Adding {0} to context'.format(ms.name))
            target.add_measurement_set(ms)

            if ms.antenna_array.name in ('EVLA', 'VLA', 'JVLA'):
                if not hasattr(context, 'evla'):
                    context.evla = collections.defaultdict(dict)

                msinfos = dict((ms.name, self._do_msinfo_heuristics(ms.name, context)) for ms in self.mses)
                context.evla['msinfo'].update(msinfos)
                context.project_summary.telescope = 'EVLA'
                context.project_summary.observatory = 'Karl G. Jansky Very Large Array'
                # context.evla['msinfo'] = { m.name : msinfo }

                # Dictionaries for per band solution intervals
                m = context.observing_run.get_ms(ms.name)
                spw2band = m.get_vla_spw2band()

                uniqueBands = set(spw2band.values())

                for bandname in uniqueBands:
                    context.evla['msinfo'][m.name].gain_solint1[bandname] = 'int'
                    context.evla['msinfo'][m.name].gain_solint2[bandname] = 'int'
                    context.evla['msinfo'][m.name].shortsol1[bandname] = 0.0
                    context.evla['msinfo'][m.name].shortsol2[bandname] = 0.0
                    context.evla['msinfo'][m.name].longsolint[bandname] = 0.0
                    context.evla['msinfo'][m.name].short_solint[bandname] = 0.0
                    context.evla['msinfo'][m.name].new_gain_solint1[bandname] = '1.0s'

        if self.setjy_results:
            for result in self.setjy_results:
                result.merge_with_context(context)

    def _do_msinfo_heuristics(self, ms, context):
        """Gets heuristics for VLA via original msinfo script
        """

        msinfo = VLAScanHeuristics(ms)
        msinfo.makescandict()
        msinfo.calibratorIntents()
        msinfo.determine3C84()

        with casa_tools.TableReader(ms) as table:
            scanNums = sorted(numpy.unique(table.getcol('SCAN_NUMBER')))

        # Check for missing scans
        missingScans = 0
        missingScanStr = ''

        for i in range(max(scanNums)):
            if scanNums.count(i + 1) == 1:
                pass
            else:
                LOG.warning("WARNING: Scan " + str(i + 1) + " is not present")
                missingScans += 1
                missingScanStr = missingScanStr + str(i + 1) + ', '

        if missingScans > 0:
            LOG.warning("WARNING: There were " + str(missingScans) + " missing scans in this MS")
        else:
            LOG.info("No missing scans found.")

        return msinfo

    def __repr__(self):
        return 'VLAImportDataResults:\n\t{0}'.format('\n\t'.join([ms.name for ms in self.mses]))


class SerialVLAImportData(importdata.ImportData):
    Inputs = VLAImportDataInputs

    def prepare(self, **parameters):
        # get results object by running super.prepare()
        results = super().prepare()

        # create results object
        myresults = VLAImportDataResults(mses=results.mses, setjy_results=results.setjy_results)

        myresults.origin = results.origin

        for ms in myresults.origin:
            if myresults.origin[ms] == 'ASDM':
                myresults.origin[ms] = 'SDM'

        PbandWarning = ''
        for ms in myresults.mses:
            for key, value in ms.get_vla_spw2band().items():
                if 'P' in value:
                    PbandWarning = 'P-band data detected in the raw data. ' \
                                   'VLA P-band pipeline calibration has not yet been ' \
                                   'commissioned and may even fail. Please inspect all P-band pipeline ' \
                                   'products carefully.'

        if PbandWarning:
            LOG.warning(PbandWarning)

        # Spectral line detection tool
        for mset in myresults.mses:
            detect_spectral_lines(mset=mset, specline_spws=self.inputs.specline_spws)
            LOG.debug("Whether spectral window is designated as spectral line or continuum.")
            for spw in mset.get_all_spectral_windows():
                LOG.debug("SPW ID {}: {}".format(spw.id, spw.specline_window))

        return myresults

    def _do_importasdm(self, asdm):
        inputs = self.inputs
        vis = self._asdm_to_vis_filename(asdm)
        outfile = os.path.join(inputs.output_dir,
                               os.path.basename(asdm) + '.flagonline.txt')

        if inputs.save_flagonline:
            # Create the standard calibration flagging template file
            template_flagsfile = os.path.join(inputs.output_dir, os.path.basename(asdm) + '.flagtemplate.txt')
            self._make_template_flagfile(template_flagsfile, 'User flagging commands file for the calibration pipeline')
            # Create the imaging targets file
            template_flagsfile = os.path.join(inputs.output_dir, os.path.basename(asdm) + '.flagtargetstemplate.txt')
            self._make_template_flagfile(template_flagsfile, 'User flagging commands file for the imaging pipeline')

        createmms = mpihelpers.parse_mpi_input_parameter(inputs.createmms)

        with_pointing_correction = getattr(inputs, 'with_pointing_correction', True)

        task = casa_tasks.importasdm(asdm=asdm,
                                     vis=vis,
                                     savecmds=inputs.save_flagonline,
                                     outfile=outfile,
                                     process_caldevice=inputs.process_caldevice,
                                     asis=inputs.asis,
                                     overwrite=inputs.overwrite,
                                     bdfflags=inputs.bdfflags,
                                     lazy=inputs.lazy,
                                     with_pointing_correction=with_pointing_correction,
                                     ocorr_mode=inputs.ocorr_mode,
                                     process_pointing=True,
                                     createmms=createmms)

        self._executor.execute(task)

        for xml_filename in ['Source.xml', 'SpectralWindow.xml', 'DataDescription.xml']:
            asdm_source = os.path.join(asdm, xml_filename)
            if os.path.exists(asdm_source):
                vis_source = os.path.join(vis, xml_filename)
                LOG.info('Copying %s from ASDM to measurement set', xml_filename)
                LOG.trace('Copying %s: %s to %s', xml_filename, asdm_source, vis_source)
                shutil.copyfile(asdm_source, vis_source)


@task_registry.set_equivalent_casa_task('hifv_importdata')
@task_registry.set_casa_commands_comment('If required, ASDMs are converted to MeasurementSets.')
class VLAImportData(sessionutils.ParallelTemplate):
    """VLAImportData class for parallelization."""

    Inputs = VLAImportDataInputs
    Task = SerialVLAImportData
