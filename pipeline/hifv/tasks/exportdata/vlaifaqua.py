import datetime
import numpy
import operator
import os
import xml.etree.ElementTree as ElementTree
from xml.etree.ElementTree import ParseError

import pipeline.domain.measures as measures
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.launcher as launcher

import pipeline.h.tasks.exportdata.aqua as aqua
from pipeline import environment
from pipeline.h.tasks.exportdata.aqua import UNDEFINED, export_to_disk
from pipeline.h.tasks.common import flagging_renderer_utils as flagutils
from pipeline.infrastructure import utils

LOG = logging.get_logger(__name__)


def aqua_report_from_file(context_file, aqua_file):
    """
    Create AQUA report from a context file on disk.
    """
    # Restore context from file
    LOG.info('Opening context file: {!s}'.format(context_file))
    context = launcher.Pipeline(context=context_file).context

    # Produce the AQUA report
    aqua_report_from_context(context, aqua_file)


def aqua_test_report_from_local_file(context_file, aqua_file):
    """
    Test AQUA report generation.
    The pipeline context file and web log directory must be in the same local directry
    """
    LOG.info('Opening context file: {!s} for test'.format(context_file))
    context = launcher.Pipeline(context=context_file, path_overrides={'name': os.path.splitext(context_file)[0],
                                                                      'output_dir': os.getcwd()}).context
    # Produce the AQUA report
    aqua_report_from_context(context, aqua_file)


def aqua_report_from_context(context, aqua_file):
    """
    Create AQUA report from a context object.
    """
    LOG.info('Recipe name: %s' % 'Unknown')
    LOG.info('    Number of stages: %d' % context.task_counter)

    # Initialize
    generator = VLAAquaXmlGenerator()
    report = generator.get_report_xml(context)

    LOG.info('Writing aqua report file: %s' % aqua_file)
    export_to_disk(report, aqua_file)


class VLAAquaXmlGenerator(aqua.AquaXmlGenerator):
    """
    Class for creating the AQUA pipeline report
    """

    def __init__(self):
        super().__init__()

    def get_report_xml(self, context):
        """
        generate XML report
        """
        report = super().get_report_xml(context)
        report.append(self.get_processing_environment())
        report.append(self.get_calibrators(context))
        report.append(self.get_science_spws(context))
        report.append(self.get_scans(context))
        report.append(self.get_observation_summary(context))
        report.append(self.get_sensitivity(context))
        report.append(self.get_checkproductsize(context))
        return report

    def get_processing_environment(self):
        """
        return XML for processing environment
        """
        root = ElementTree.Element('ProcessingEnvironment')
        nodes = environment.cluster_details()
        nx = ElementTree.Element("ExecutionMode")
        nmpiservers = None
        hostlist = []
        if len(nodes) > 1:
            nx.text = "parallel"
            nmpiservers = ElementTree.Element("MPIServers")
            nmpiservers.text = str(len(nodes))
        else:
            nx.text = "serial"
        root.append(nx)
        if nmpiservers is not None:
            root.append(nmpiservers)

        for node in nodes:
            if node.hostname not in hostlist:
                nx = ElementTree.Element("Host")
                ElementTree.SubElement(nx, "HostName").text = node.hostname
                ElementTree.SubElement(nx, "OperatingSystem").text = node.host_distribution
                ElementTree.SubElement(nx, "Cores").text = str(node.casa_cores)
                ElementTree.SubElement(nx, "Memory").text = str(measures.FileSize(node.casa_memory, measures.FileSizeUnits.BYTES))
                ElementTree.SubElement(nx, "CPU").text = str(node.cpu_type)
                root.append(nx)
                hostlist.append(node.hostname)
        return root

    def get_calibrators(self, context):
        """
        return XML for calibrators
        """
        mslist = context.observing_run.get_measurement_sets()
        root = ElementTree.Element("Calibrators")

        for ms in mslist:
            if ms.name not in context.evla['msinfo']:
                continue
            if len(context.evla['msinfo'][ms.name].spindex_results) != 0:
                for calibrator in context.evla['msinfo'][ms.name].spindex_results:
                    nx = ElementTree.Element("Calibrator")
                    ElementTree.SubElement(nx, 'Name').text = calibrator["source"]
                    ElementTree.SubElement(nx, 'Fitorder').text = calibrator["fitorder"]
                    if isinstance(calibrator["fitflx"], list):
                        ElementTree.SubElement(nx, 'FluxDensity').text = ','.join([str(fitflx) for fitflx in calibrator["fitflx"]])
                    else:
                        ElementTree.SubElement(nx, 'FluxDensity').text = str(calibrator["fitflx"])

                    ElementTree.SubElement(nx, 'SpectralIndex').text = str(calibrator["spix"])
                    root.append(nx)

                    source_intents = self.get_source_intents(ms, calibrator["source"])
                    if source_intents is not None:
                        ElementTree.SubElement(nx, 'Intents').text = source_intents
                    else:
                        LOG.warning("Unable to get source intents for AQUA report")

        return root

    def get_source_intents(self, ms, source):
        """
        return XML for source intents
        """
        source_intents = None
        for s in ms.sources:
            if s.name == source:
                source_intents = ",".join(s.intents)
                break
        return source_intents

    def get_science_spws(self, context):
        """
        return XML for science SPWs
        """
        mslist = context.observing_run.get_measurement_sets()
        root = ElementTree.Element("ScienceSPWs")
        for ms in mslist:
            spwlist = ms.get_spectral_windows(science_windows_only=True)
            for spw in spwlist:
                channel0 = spw.channels.chan_freqs[0]
                NChannels = len(spw.channels.chan_freqs)

                chan_diff = numpy.diff(spw.channels.chan_freqs)
                if NChannels != 0 and numpy.allclose(chan_diff, chan_diff[0]):
                    ChannelWidth = chan_diff[0]
                else:
                    LOG.warning("Channels are not equally spaced. Setting channel width to median of channel differences.")
                    ChannelWidth = numpy.median(numpy.abs(chan_diff))
                nx = ElementTree.Element("SPW")
                ElementTree.SubElement(nx, 'Channel0', Units="Hz").text = str(channel0)
                ElementTree.SubElement(nx, 'ChannelWidth', Units="Hz").text = str(ChannelWidth)
                ElementTree.SubElement(nx, 'NChannels').text = str(NChannels)
                root.append(nx)

        return root

    def get_scans(self, context):
        """
        return XML for scan information
        """
        mslist = context.observing_run.get_measurement_sets()
        root = ElementTree.Element("Scans")
        for ms in mslist:
            scans = ms.scans
            for sc in scans:
                nx = ElementTree.Element("Scan")
                ElementTree.SubElement(nx, 'ID').text = str(sc.id)
                ElementTree.SubElement(nx, 'Start').text = str(sc.start_time["m0"]["value"])
                ElementTree.SubElement(nx, 'End').text = str(sc.end_time["m0"]["value"])
                ElementTree.SubElement(nx, 'SPWIDs').text = ",".join(str(spw.id) for spw in sorted(sc.spws, key=lambda x: x.id))
                ElementTree.SubElement(nx, 'FieldIDs').text = ",".join([str(field.id) for field in sc.fields])
                ElementTree.SubElement(nx, 'Intents').text = ",".join([str(intent) for intent in sc.intents])
                root.append(nx)

        return root

    def get_observation_summary(self, context):
        """
        return XML for observation summary
        """
        mslist = context.observing_run.get_measurement_sets()
        root = ElementTree.Element("ObservationSummary")

        for ms in mslist:
            if ms.name not in context.evla['msinfo'].keys():
                continue
            nx = ElementTree.Element("StartTime")
            nx.text = str(ms.start_time["m0"]["value"])
            root.append(nx)

            nx = ElementTree.Element("EndTime")
            nx.text = str(ms.end_time["m0"]["value"])
            root.append(nx)

            nx = ElementTree.Element("Baseline")
            ElementTree.SubElement(nx, "Min").text = str(ms.antenna_array.baseline_min.length.value)
            ElementTree.SubElement(nx, "Max").text = str(ms.antenna_array.baseline_max.length.value)
            root.append(nx)

            nx = ElementTree.Element("FlaggedFraction")
            dict_flagged_fraction = self.get_flagged_fraction(context)
            nx_flagdata = ElementTree.SubElement(nx, "Flagdata")
            for msname in dict_flagged_fraction:
                for reason in dict_flagged_fraction[msname]:
                    ElementTree.SubElement(nx_flagdata, reason).text = str(dict_flagged_fraction[msname][reason])
            dict_field_flagged_fraction = self.get_stwt_flagged_fraction(context)
            nx_statwt = ElementTree.SubElement(nx, "StatWt")
            for target, fraction in dict_field_flagged_fraction.items():
                sub_element = ElementTree.SubElement(nx_statwt, "Target", name=target)
                sub_element.text = str(fraction)
            root.append(nx)

            science_scans = [scan for scan in ms.scans if 'TARGET' in scan.intents]
            time_on_source = utils.total_time_on_source(science_scans)
            nx = ElementTree.Element("TimeOnSource", Units="sec")
            nx.text = str(time_on_source.total_seconds())
            root.append(nx)

            target_exposure = {}
            for sc in science_scans:
                for field in sc.fields:
                    if field.name not in target_exposure:
                        target_exposure[field.name] = datetime.timedelta(0)

                    target_exposure[field.name] += sc.time_on_source

            nx = ElementTree.Element("TimeOnScienceTarget")
            for target, exposure in target_exposure.items():
                sub_element = ElementTree.SubElement(nx, "Target", name=target, Units="sec")
                sub_element.text = str(exposure.seconds)

            root.append(nx)

            el_min = ms.compute_az_el_for_ms(min)[1]
            el_max = ms.compute_az_el_for_ms(max)[1]
            nx = ElementTree.Element("Elevation")
            ElementTree.SubElement(nx, "Min").text = str(el_min)
            ElementTree.SubElement(nx, "Max").text = str(el_max)
            root.append(nx)
            target_elevation = {}
            for sc in science_scans:
                for field in sc.fields:
                    if field.name not in target_elevation:
                        target_elevation[field.name] = []
                    target_elevation[field.name].append(ms.compute_az_el_to_field(field, sc.start_time)[1])
                    target_elevation[field.name].append(ms.compute_az_el_to_field(field, sc.end_time)[1])

            nx = ElementTree.Element("TargetElevation")
            for target, elevation in target_elevation.items():
                sub_element = ElementTree.SubElement(nx, "Target", name=target)
                min_sub_element = ElementTree.SubElement(sub_element, "Min")
                min_sub_element.text = str(min(elevation))
                max_sub_element = ElementTree.SubElement(sub_element, "Max")
                max_sub_element.text = str(max(elevation))
            root.append(nx)

            nx = ElementTree.Element("NAntennas")
            nx.text = str(len(ms.antennas))
            root.append(nx)

        return root

    def get_flagged_fraction(self, context):
        """
        return flagged fraction
        """
        flagdata_results = []
        output_dict = {}

        for result in context.results:
            objresult = result.read()
            if objresult.taskname == "hifv_flagdata":
                flagdata_results = objresult

        for flagdata_result in flagdata_results:
            intents_to_summarise = flagutils.intents_to_summarise(context)
            flag_table_intents = ['TOTAL', 'SCIENCE SPWS']
            flag_table_intents.extend(intents_to_summarise)
            flag_totals = {}
            flag_totals = utils.dict_merge(flag_totals, flagutils.flags_for_result(flagdata_result, context, intents_to_summarise=intents_to_summarise))
            reasons_to_export = ['online', 'shadow', 'qa0', 'qa2', 'before',
                                 'template', 'intents', 'autocorr', 'edgespw',
                                 'clip', 'quack']
            for ms in flag_totals:
                output_dict[ms] = {}
                for reason in flag_totals[ms]:
                    for intent in flag_totals[ms][reason]:
                        if reason in reasons_to_export:
                            if "TOTAL" in intent:
                                new = float(flag_totals[ms][reason][intent][0])
                                total = float(flag_totals[ms][reason][intent][1])
                                percentage = new/total
                                output_dict[ms][reason] = percentage
        return output_dict

    def get_stwt_flagged_fraction(self, context):
        """
            return flagged fraction in hifv_statwt task
        """

        output_dict = {}
        statwt_results = []
        for result in context.results:
            objresult = result.read()
            if objresult.taskname == "hifv_statwt":
                statwt_results = objresult

        for statwt_result in statwt_results:
            for summary in statwt_result.summaries:
                if summary["name"] == "statwt":
                    for field in summary["field"]:
                        output_dict[field] = float(summary["field"][field]['flagged']/summary["field"][field]["total"])
        return output_dict

    def get_project_structure(self, context):
        # get base XML from base class
        root = super().get_project_structure(context)

        # add our ALMA-specific elements
        ElementTree.SubElement(root, 'OusEntityId').text = context.project_structure.ous_entity_id
        ElementTree.SubElement(root, 'OusPartId').text = context.project_structure.ous_part_id
        ElementTree.SubElement(root, 'OusStatusEntityId').text = context.project_structure.ousstatus_entity_id

        return root

    def get_calibration_topic(self, context, topic_results):
        # get base XML from base class
        xml_root = super().get_calibration_topic(context, topic_results)

        m = {
            'hifa_gfluxscale': (operator.attrgetter('measurements'), lambda r: str(r.qa.representative.score))
        }
        flux_xml = flux_xml_for_stages(context, topic_results, m)
        xml_root.extend(flux_xml)

        return xml_root

    def get_dataset_topic(self, context, topic_results):
        # get base XML from base class
        xml_root = super().get_dataset_topic(context, topic_results)

        m = {
            'hifv_importdata': (lambda x: x.setjy_results[0].measurements, lambda _: UNDEFINED),
        }
        flux_xml = flux_xml_for_stages(context, topic_results, m)
        # omit containing flux measurement element if no measurements were found
        if len(list(flux_xml)) > 0:
            xml_root.extend(flux_xml)

        sensitivity_xml = aqua.sensitivity_xml_for_stages(context, topic_results)
        # omit containing element if no measurements were found
        if len(list(sensitivity_xml)) > 0:
            xml_root.extend(sensitivity_xml)

        return xml_root

    def get_sensitivity(self, context):
        """
            return xml for image sensitivity
        """
        root = ElementTree.Element("Imaging")

        for result in context.results:
            topic = result.read()
            if topic.taskname != "hif_makeimages":
                continue

            sensitivities = topic.sensitivities_for_aqua
            for index, sensitivity in enumerate(sensitivities):
                nx = ElementTree.Element("image")

                simple_tags = [
                    "array", "intent", "field", "spw",
                    "is_representative", "bwmode", "cell",
                    "robust", "datatype"
                ]

                for tag in simple_tags:
                    try:
                        value = sensitivity.get(tag, 'N/A')
                        ElementTree.SubElement(nx, tag).text = str(value)
                    except (KeyError, AttributeError, TypeError) as e:
                        raise ParseError(f"Error processing '{tag}': {e}")

                nested_tags = [
                    ("bandwidth", nx),
                    ("observed_sensitivity", nx),
                    ("effective_bw", nx),
                    ("pbcor_image_min", nx),
                    ("pbcor_image_max", nx),
                    ("theoretical_sensitivity", nx if index < len(topic.results) else None),
                ]
                for tag, nx in nested_tags:
                    if nx is None:
                        continue
                    try:
                        data = sensitivity.get(tag)
                        if data is None or "value" not in data or "unit" not in data:
                            ElementTree.SubElement(nx, tag).text = 'N/A'
                        else:
                            ElementTree.SubElement(
                                nx, tag, Units=str(data["unit"])
                            ).text = str(data["value"])
                    except (KeyError, AttributeError, TypeError) as e:
                        raise ParseError(f"Error processing '{tag}': {e}")

                try:
                    bw = sensitivity.get("bandwidth")
                    if bw is None or "value" not in bw or "unit" not in bw:
                        ElementTree.SubElement(nx, "bandwidth").text = 'N/A'
                    else:
                        ElementTree.SubElement(
                            nx, "bandwidth", Units=str(bw["unit"])
                        ).text = str(bw["value"])
                except (KeyError, AttributeError, TypeError) as e:
                    raise ParseError(f"Error processing 'bandwidth': {e}")

                nx_beam = ElementTree.SubElement(nx, "beam")
                beam_tags = ["major", "minor"]
                for tag in beam_tags:
                    try:
                        data = sensitivity["beam"][tag]
                        if data is None or "value" not in data or "unit" not in data:
                            ElementTree.SubElement(nx_beam, tag).text = 'N/A'
                        else:
                            ElementTree.SubElement(
                                nx_beam, tag, Units=str(data["unit"])
                            ).text = str(data["value"])
                    except (KeyError, AttributeError, TypeError) as e:
                        raise ParseError(f"Error processing 'beam.major': {e}")

                root.append(nx)

        return root

    def get_checkproductsize(self, context):
        """
            return xml for data volume
        """
        root = ElementTree.Element("DataVolume")
        nx = ElementTree.Element("ProductsDirectory", Units="MB")
        size_products_dir = utils.get_directory_size(context.products_dir)
        nx.text = "{:.2f}".format(size_products_dir)
        root.append(nx)
        for result in context.results:
            result = result.read()
            if result.taskname == "hif_checkproductsize":
                nx = ElementTree.Element("AllowedMaxCubeSize", Units="MB")
                nx.text = str(result.allowed_maxcubesize * 1024 if result.allowed_maxcubesize != -1 else -1)
                root.append(nx)
                nx = ElementTree.Element("AllowedMaxCubeLimit", Units="MB")
                nx.text = str(result.allowed_maxcubelimit * 1024 if result.allowed_maxcubelimit != -1 else -1)
                root.append(nx)
                nx = ElementTree.Element("PredictedMaxCubeSize", Units="MB")
                nx.text = str(result.original_maxcubesize * 1024 if result.original_maxcubesize != -1 else -1)
                root.append(nx)
                nx = ElementTree.Element("MitigatedMaxCubeSize", Units="MB")
                nx.text = str(result.mitigated_maxcubesize * 1024 if result.mitigated_maxcubesize != -1 else -1)
                root.append(nx)
                nx = ElementTree.Element("AllowedMaxProductSize", Units="MB")
                nx.text = str(result.allowed_productsize * 1024 if result.allowed_productsize != -1 else -1)
                root.append(nx)
                nx = ElementTree.Element("InitialProductSize", Units="MB")
                nx.text = str(result.original_productsize * 1024 if result.original_productsize != -1 else -1)
                root.append(nx)
                nx = ElementTree.Element("MitigatedProductSize", Units="MB")
                nx.text = str(result.mitigated_productsize * 1024 if result.mitigated_productsize != -1 else -1)
                root.append(nx)
        return root

    def get_imaging_topic(self, context, topic_results):
        """
        Get the XML for the imaging topic.

        :param context: pipeline context
        :param topic_results: list of Results for this topic
        :return: XML for imaging topic
        :rtype: xml.etree.cElementTree.Element
        """
        # get base XML from base class
        xml_root = super().get_imaging_topic(context, topic_results)

        sensitivity_xml = aqua.sensitivity_xml_for_stages(context, topic_results, name='ImageSensitivities')
        # omit containing element if no measurements were found
        if len(list(sensitivity_xml)) > 0:
            xml_root.extend(sensitivity_xml)

        return xml_root


def flux_xml_for_stages(context, results, accessor_dict):
    """
    Get the XML for flux measurements contained in a list of results.

    This function is a higher-order function; it expects to be given a dict
    of accessor functions, which it uses to access the flux measurements and
    QA score of the appropriate results. 'Appropriate' means that the task
    name matches the dict key. This lets the function call different accessor
    functions for different types of result.

    The dict accessor dict uses task names as keys, with values as two-tuples
    comprising

        1. a function to access the flux measurements for a result
        2. a function to access the QA score for that result

    :param context: pipeline context
    :param results: results to process
    :param accessor_dict: dict of accessor functions
    :return: XML for flux measurements
    :rtype: xml.etree.ElementTree.Element
    """
    xml_root = ElementTree.Element('FluxMeasurements')

    for result in results:
        pipeline_casa_task = result.pipeline_casa_task
        for task_name, (flux_accessor, score_accessor) in accessor_dict.items():
            # need parenthesis to distinguish between cases such as
            # hifa_gfluxscale and hifa_gfluxscaleflag
            if pipeline_casa_task.startswith(task_name + '('):
                flux_xml = xml_for_flux_stage(context, result, task_name, flux_accessor, score_accessor)
                xml_root.append(flux_xml)

    return xml_root


def xml_for_flux_stage(context, stage_results, origin, accessor, score_accessor):
    """
    Get the XML for all flux measurements contained in a ResultsList.

    :param context: pipeline context
    :param stage_results: ResultList containing flux results to summarise
    :param origin: text for Origin attribute value
    :param accessor: function that returns the flux measurements from the Result
    :param score_accessor: function that returns the QA score for the Result
    :rtype: xml.etree.ElementTree.Element
    """
    score = score_accessor(stage_results)
    xml_root = ElementTree.Element('FluxMeasurements', Origin=origin, Score=score)

    for result in stage_results:
        vis = os.path.basename(result.inputs['vis'])
        ms_for_result = context.observing_run.get_ms(vis)
        measurements = accessor(result)
        ms_xml = xml_for_extracted_flux_measurements(measurements, ms_for_result)
        xml_root.extend(ms_xml)

    return xml_root


def xml_for_extracted_flux_measurements(all_measurements, ms):
    """
    Get the XML for a set of flux measurements extracted from a Result.

    :param all_measurements: flux measurements dict.
    :param ms: measurement set
    :return: XML
    :rtype: xml.etree.ElementTree.Element
    """
    asdm = aqua.vis_to_asdm(ms.name)

    result = []
    for field_id, field_measurements in all_measurements.items():
        field = ms.get_fields(field_id)[0]
        field_name = field.name

        if field_name.startswith('"') and field_name.endswith('"'):
            field_name = field_name[1:-1]

        for measurement in sorted(field_measurements, key=lambda m: int(m.spw_id)):
            spw = ms.get_spectral_window(measurement.spw_id)
            freq_ghz = '{:.6f}'.format(spw.centre_frequency.to_units(measures.FrequencyUnits.GIGAHERTZ))

            # I only for now ...
            for stokes in ['I']:
                try:
                    flux = getattr(measurement, stokes)
                    flux_jy = flux.to_units(measures.FluxDensityUnits.JANSKY)
                    flux_jy = '{:.3f}'.format(flux_jy)
                except:
                    continue

                try:
                    unc = getattr(measurement.uncertainty, stokes)
                    unc_jy = unc.to_units(measures.FluxDensityUnits.JANSKY)
                    if unc_jy != 0:
                        unc_jy = '{:.6f}'.format(unc_jy)
                    else:
                        unc_jy = ''
                except:
                    unc_jy = ''

                xml = ElementTree.Element('FluxMeasurement',
                                          SpwName=spw.name,
                                          MsSpwId=str(spw.id),
                                          FluxJy=flux_jy,
                                          ErrorJy=unc_jy,
                                          Asdm=asdm,
                                          Field=field_name,
                                          FrequencyGHz=freq_ghz)
                result.append(xml)

    return result


def _hifa_preimagecheck_sensitivity_exporter(stage_results):
    # XML exporter expects this function to return a list of dictionaries
    l = []
    for result in stage_results:
        l.extend(result.sensitivities_for_aqua)
    return l


aqua.TASK_NAME_TO_SENSITIVITY_EXPORTER['hifa_imageprecheck'] = _hifa_preimagecheck_sensitivity_exporter
