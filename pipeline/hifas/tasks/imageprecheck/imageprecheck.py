import math

import pipeline.domain.measures as measures
import pipeline.hifa.tasks.imageprecheck.imageprecheck as hifa_task_imageprecheck
import pipeline.infrastructure as infrastructure
#import pipeline.infrastructure.api as api
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.h.tasks.common.sensitivity import Sensitivity
from pipeline.hif.heuristics import imageparams_factory
from pipeline.hifa.heuristics import imageprecheck
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry

LOG = infrastructure.get_logger(__name__)


class ImagePreCheckResults(hifa_task_imageprecheck.ImagePreCheckResults):
    def __init__(self, real_repr_target=False, repr_target='', repr_source='', repr_spw=None,
                 reprBW_mode=None, reprBW_nbin=None,
                 minAcceptableAngResolution='0.0arcsec', maxAcceptableAngResolution='0.0arcsec',
                 maxAllowedBeamAxialRatio=0.0, user_minAcceptableAngResolution='0.0arcsec',
                 user_maxAcceptableAngResolution='0.0arcsec', user_maxAllowedBeamAxialRatio=0.0,
                 sensitivityGoal='0mJy', hm_robust=0.5, hm_uvtaper=[],
                 sensitivities=None, sensitivity_bandwidth=None, score=None, single_continuum=False,
                 per_spw_cont_sensitivities_all_chan=None, synthesized_beams=None, beamRatios=None,
                 error=False, error_msg=None):
        super(ImagePreCheckResults, self).__init__()

        if sensitivities is None:
            sensitivities = []

        self.real_repr_target = real_repr_target
        self.repr_target = repr_target
        self.repr_source = repr_source
        self.repr_spw = repr_spw
        self.reprBW_mode = reprBW_mode
        self.reprBW_nbin = reprBW_nbin
        self.minAcceptableAngResolution = minAcceptableAngResolution
        self.maxAcceptableAngResolution = maxAcceptableAngResolution
        self.maxAllowedBeamAxialRatio = maxAllowedBeamAxialRatio
        self.sensitivityGoal = sensitivityGoal
        self.hm_robust = hm_robust
        self.hm_uvtaper = hm_uvtaper
        self.sensitivities = sensitivities
        self.sensitivities_for_aqua = []
        self.sensitivity_bandwidth = sensitivity_bandwidth
        self.score = score
        self.single_continuum = single_continuum
        self.per_spw_cont_sensitivities_all_chan = per_spw_cont_sensitivities_all_chan
        self.synthesized_beams = synthesized_beams
        self.beamRatios = beamRatios
        self.error = error
        self.error_msg = error_msg

        # Update these values for the weblog
        self.user_minAcceptableAngResolution = user_minAcceptableAngResolution
        self.user_maxAcceptableAngResolution = user_maxAcceptableAngResolution
        self.user_maxAllowedBeamAxialRatio = user_maxAllowedBeamAxialRatio

    def merge_with_context(self, context):
        """
        See :method:`~pipeline.infrastructure.api.Results.merge_with_context`
        """
        # Store uvtaper parameter in context
        if 'uvtaper' in context.imaging_parameters.keys():
            del(context.imaging_parameters['uvtaper'])
        if self.hm_uvtaper != []:
            context.imaging_parameters['uvtaper'] = self.hm_uvtaper

        # Call base method
        super().merge_with_context(context)


class ImagePreCheckInputs(vdp.StandardInputs):
    # Search order of input vis
    processing_data_type = [DataType.REGCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_ALL, DataType.RAW]

    calcsb = vdp.VisDependentProperty(default=False)
    parallel = vdp.VisDependentProperty(default='automatic')
    desired_angular_resolution = vdp.VisDependentProperty(default='')
    def __init__(self, context, vis=None, desired_angular_resolution=None, calcsb=None, parallel=None):
        self.context = context
        self.vis = vis
        self.desired_angular_resolution = desired_angular_resolution
        self.calcsb = calcsb
        self.parallel = parallel


# tell the infrastructure to give us mstransformed data when possible by
# registering our preference for imaging measurement sets
#api.ImagingMeasurementSetsPreferred.register(ImagePreCheckInputs)


@task_registry.set_equivalent_casa_task('hifas_imageprecheck')
class ImagePreCheck(hifa_task_imageprecheck.ImagePreCheck):
    Inputs = ImagePreCheckInputs

    is_multi_vis_task = True

    def prepare(self):
        '''
        Differences compared to base task (hifa_task_imageprecheck.ImagePreCheck) prepare method:

        - user speciefed angular resultion goal can be set via inputs.desired_angular_resolution
        - uvtaper is computed if the best robust is 2.0 and inputs.desired_angular_resolution was set
        - return best robust if repr_target=False, base method returns robust=0.5 in this case
        - if repr_target=False and best robust value is 2.0, then compute and return uvtaper
        '''
        inputs = self.inputs
        context = self.inputs.context

        cqa = casa_tools.quanta

        calcsb = inputs.calcsb
        parallel = inputs.parallel

        known_per_spw_cont_sensitivities_all_chan = context.per_spw_cont_sensitivities_all_chan
        known_synthesized_beams = context.synthesized_beams

        imageprecheck_heuristics = imageprecheck.ImagePreCheckHeuristics(inputs)

        image_heuristics_factory = imageparams_factory.ImageParamsHeuristicsFactory()
        image_heuristics = image_heuristics_factory.getHeuristics(
            vislist=inputs.vis,
            spw='',
            observing_run=context.observing_run,
            imagename_prefix=context.project_structure.ousstatus_entity_id,
            proj_params=context.project_performance_parameters,
            contfile=context.contfile,
            linesfile=context.linesfile,
            imaging_params=context.imaging_parameters,
            imaging_mode='ALMA'
        )

        repr_target, repr_source, repr_spw, repr_freq, reprBW_mode, real_repr_target, minAcceptableAngResolution, maxAcceptableAngResolution, maxAllowedBeamAxialRatio, sensitivityGoal = image_heuristics.representative_target()

        # PIPE-708, used only for SRDP, see hifas_imageprecheck task
        if inputs.desired_angular_resolution not in [None, '']:
            # Parse user angular resolution goal
            if type(inputs.desired_angular_resolution) == str:
                userAngResolution = cqa.quantity(inputs.desired_angular_resolution)
            else:
                userAngResolution = cqa.quantity('%.3garcsec' % inputs.desired_angular_resolution)
            # Assume symmetric beam for now
            user_desired_beam = {'minor': cqa.convert(userAngResolution, 'arcsec'),
                                 'major': cqa.convert(userAngResolution, 'arcsec'),
                                 'positionangle': '0.0deg'}
            # Determine
            userAngResolution = cqa.sqrt(cqa.div(cqa.add(cqa.pow(user_desired_beam['minor'],2),
                                                         cqa.pow(user_desired_beam['major'],2)),
                                                 2.0))
            LOG.info('Setting user specified desired angular resolution to %s' % cqa.tos(userAngResolution))
        else:
            userAngResolution = cqa.quantity('%.3garcsec' % 0.0)

        # Store PI selected angular resolution
        pi_minAcceptableAngResolution = minAcceptableAngResolution
        pi_maxAcceptableAngResolution = maxAcceptableAngResolution
        pi_maxAllowedBeamAxialRatio = maxAllowedBeamAxialRatio

        # Store user selected angular resolution
        user_minAcceptableAngResolution = cqa.mul(userAngResolution, 0.8)
        user_maxAcceptableAngResolution = cqa.mul(userAngResolution, 1.2)
        user_maxAllowedBeamAxialRatio = maxAllowedBeamAxialRatio

        # Use user selected angular resolution for calculation, if specified
        if cqa.getvalue(userAngResolution)[0] != 0.0:
            minAcceptableAngResolution = user_minAcceptableAngResolution
            maxAcceptableAngResolution = user_maxAcceptableAngResolution
            maxAllowedBeamAxialRatio = user_maxAllowedBeamAxialRatio

        repr_field = list(image_heuristics.field_intent_list('TARGET', repr_source))[0][0]

        repr_ms = self.inputs.ms[0]
        real_repr_spw = context.observing_run.virtual2real_spw_id(int(repr_spw), repr_ms)
        real_repr_spw_obj = repr_ms.get_spectral_window(real_repr_spw)
        single_continuum = any(['Single_Continuum' in t for t in real_repr_spw_obj.transitions])

        # Get the array
        diameter = min([a.diameter for a in repr_ms.antennas])
        if diameter == 7.0:
            array = '7m'
            robust_values_to_check = [0.5]
        else:
            array = '12m'
            robust_values_to_check = [0.0, 0.5, 1.0, 2.0]

        # Approximate reprBW with nbin
        if reprBW_mode in ['nbin', 'repr_spw']:
            physicalBW_of_1chan = float(real_repr_spw_obj.channels[0].getWidth().convert_to(measures.FrequencyUnits.HERTZ).value)
            nbin = int(cqa.getvalue(cqa.convert(repr_target[2], 'Hz'))/physicalBW_of_1chan + 0.5)
            cont_sens_bw_modes = ['aggBW']
            scale_aggBW_to_repBW = False
        elif reprBW_mode == 'multi_spw':
            nbin = -1
            cont_sens_bw_modes = ['repBW', 'aggBW']
            scale_aggBW_to_repBW = True
        else:
            nbin = -1
            cont_sens_bw_modes = ['repBW', 'aggBW']
            scale_aggBW_to_repBW = False

        primary_beam_size = image_heuristics.largest_primary_beam_size(spwspec=str(repr_spw), intent='TARGET')
        gridder = image_heuristics.gridder('TARGET', repr_field)
        field_ids = image_heuristics.field('TARGET', repr_field)
        cont_spwids = sorted(context.observing_run.virtual_science_spw_ids)
        repr_field_obj = repr_ms.get_fields(repr_field, intent='TARGET')[0]
        filtered_cont_spwids = sorted(
            [context.observing_run.real2virtual_spw_id(s.id, repr_ms) for s in repr_field_obj.valid_spws
             if context.observing_run.real2virtual_spw_id(s.id, repr_ms) in list(map(int, cont_spwids))])
        cont_spw = ','.join(map(str, filtered_cont_spwids))
        num_cont_spw = len(filtered_cont_spwids)

        # Get default heuristics uvtaper value
        default_uvtaper = image_heuristics.uvtaper()
        beams = {(0.0, str(default_uvtaper), 'repBW'): None, \
                 (0.5, str(default_uvtaper), 'repBW'): None, \
                 (1.0, str(default_uvtaper), 'repBW'): None, \
                 (2.0, str(default_uvtaper), 'repBW'): None, \
                 (0.0, str(default_uvtaper), 'aggBW'): None, \
                 (0.5, str(default_uvtaper), 'aggBW'): None, \
                 (1.0, str(default_uvtaper), 'aggBW'): None, \
                 (2.0, str(default_uvtaper), 'aggBW'): None}
        cells = {}
        imsizes = {}
        sensitivities = []
        sensitivity_bandwidth = None
        for robust in robust_values_to_check:
            # Calculate nbin / reprBW sensitivity if necessary
            if reprBW_mode in ['nbin', 'repr_spw']:

                beams[(robust, str(default_uvtaper), 'repBW')], known_synthesized_beams = image_heuristics.synthesized_beam(
                    [(repr_field, 'TARGET')], str(repr_spw), robust=robust, uvtaper=default_uvtaper,
                    known_beams=known_synthesized_beams, force_calc=calcsb, parallel=parallel, shift=True)

                # If the beam is invalid, error and return.
                if beams[(robust, str(default_uvtaper), 'repBW')] == 'invalid':
                    LOG.error('Beam for repBW and robust value of %.1f is invalid. Cannot continue.' % robust)
                    return ImagePreCheckResults(error=True, error_msg='Invalid beam')

                cells[(robust, str(default_uvtaper), 'repBW')] = image_heuristics.cell(beams[(robust, str(default_uvtaper), 'repBW')])
                imsizes[(robust, str(default_uvtaper), 'repBW')] = image_heuristics.imsize(field_ids, cells[(robust, str(default_uvtaper), 'repBW')], primary_beam_size, centreonly=False, intent='TARGET')

                try:
                    sensitivity, eff_ch_bw, sens_bw, known_per_spw_cont_sensitivities_all_chan = \
                        image_heuristics.calc_sensitivities(inputs.vis, repr_field, 'TARGET', str(repr_spw), nbin, {}, 'cube', gridder, cells[(robust, str(default_uvtaper), 'repBW')], imsizes[(robust, str(default_uvtaper), 'repBW')], 'briggs', robust, default_uvtaper, True, known_per_spw_cont_sensitivities_all_chan, calcsb)
                    # Set calcsb flag to False since the first calculations of beam
                    # and sensitivity will have already reset the dictionaries.
                    calcsb = False
                    sensitivities.append(Sensitivity(
                        array=array,
                        intent='TARGET',
                        field=repr_field,
                        spw=str(repr_spw),
                        is_representative=True,
                        bandwidth=cqa.quantity(sens_bw, 'Hz'),
                        bwmode='repBW',
                        beam=beams[(robust, str(default_uvtaper), 'repBW')],
                        cell=[cqa.convert(cells[(robust, str(default_uvtaper), 'repBW')][0], 'arcsec'),
                              cqa.convert(cells[(robust, str(default_uvtaper), 'repBW')][0], 'arcsec')],
                        robust=robust,
                        uvtaper=default_uvtaper,
                        sensitivity=cqa.quantity(sensitivity, 'Jy/beam')))
                except:
                    sensitivities.append(Sensitivity(
                        array=array,
                        intent='TARGET',
                        field=repr_field,
                        spw=str(repr_spw),
                        is_representative=True,
                        bandwidth=cqa.quantity(0.0, 'Hz'),
                        bwmode='repBW',
                        beam=beams[(robust, str(default_uvtaper), 'repBW')],
                        cell=['0.0 arcsec', '0.0 arcsec'],
                        robust=robust,
                        uvtaper=default_uvtaper,
                        sensitivity=cqa.quantity(0.0, 'Jy/beam')))
                    sens_bw = 0.0

                sensitivity_bandwidth = cqa.quantity(sens_bw, 'Hz')

            beams[(robust, str(default_uvtaper), 'aggBW')], known_synthesized_beams = image_heuristics.synthesized_beam(
                [(repr_field, 'TARGET')], cont_spw, robust=robust, uvtaper=default_uvtaper,
                known_beams=known_synthesized_beams, force_calc=calcsb, parallel=parallel, shift=True)

            # If the beam is invalid, error and return.
            if beams[(robust, str(default_uvtaper), 'aggBW')] == 'invalid':
                LOG.error('Beam for aggBW and robust value of %.1f is invalid. Cannot continue.' % robust)
                return ImagePreCheckResults(error=True, error_msg='Invalid beam')

            cells[(robust, str(default_uvtaper), 'aggBW')] = image_heuristics.cell(beams[(robust, str(default_uvtaper), 'aggBW')])
            imsizes[(robust, str(default_uvtaper), 'aggBW')] = image_heuristics.imsize(field_ids, cells[(robust, str(default_uvtaper), 'aggBW')], primary_beam_size, centreonly=False, intent='TARGET')

            # Calculate full cont sensitivity (no frequency ranges excluded)
            try:
                sensitivity, eff_ch_bw, sens_bw, known_per_spw_cont_sensitivities_all_chan = \
                    image_heuristics.calc_sensitivities(inputs.vis, repr_field, 'TARGET', cont_spw, -1, {}, 'cont', gridder, cells[(robust, str(default_uvtaper), 'aggBW')], imsizes[(robust, str(default_uvtaper), 'aggBW')], 'briggs', robust, default_uvtaper, True, known_per_spw_cont_sensitivities_all_chan, calcsb)
                # Set calcsb flag to False since the first calculations of beam
                # and sensitivity will have already reset the dictionaries.
                calcsb = False
                for cont_sens_bw_mode in cont_sens_bw_modes:
                    if scale_aggBW_to_repBW and cont_sens_bw_mode == 'repBW':
                        # Handle scaling to repSPW_BW < repBW <= 0.9 * aggBW case
                        _bandwidth = repr_target[2]
                        _sensitivity = cqa.mul(cqa.quantity(sensitivity, 'Jy/beam'), cqa.sqrt(cqa.div(cqa.quantity(sens_bw, 'Hz'), repr_target[2])))
                    else:
                        _bandwidth = cqa.quantity(min(sens_bw, num_cont_spw * 1.875e9), 'Hz')
                        _sensitivity = cqa.quantity(sensitivity, 'Jy/beam')

                    sensitivities.append(Sensitivity(
                        array=array,
                        intent='TARGET',
                        field=repr_field,
                        spw=cont_spw,
                        is_representative=True,
                        bandwidth=_bandwidth,
                        bwmode=cont_sens_bw_mode,
                        beam=beams[(robust, str(default_uvtaper), 'aggBW')],
                        cell=[cqa.convert(cells[(robust, str(default_uvtaper), 'aggBW')][0], 'arcsec'),
                              cqa.convert(cells[(robust, str(default_uvtaper), 'aggBW')][0], 'arcsec')],
                        robust=robust,
                        uvtaper=default_uvtaper,
                        sensitivity=_sensitivity))
            except Exception as e:
                for _ in cont_sens_bw_modes:
                    sensitivities.append(Sensitivity(
                        array=array,
                        intent='TARGET',
                        field=repr_field,
                        spw=cont_spw,
                        is_representative=True,
                        bandwidth=cqa.quantity(0.0, 'Hz'),
                        bwmode='aggBW',
                        beam=beams[(robust, str(default_uvtaper), 'aggBW')],
                        cell=['0.0 arcsec', '0.0 arcsec'],
                        robust=robust,
                        uvtaper=default_uvtaper,
                        sensitivity=cqa.quantity(0.0, 'Jy/beam')))
                sens_bw = 0.0

            if sensitivity_bandwidth is None:
                sensitivity_bandwidth = cqa.quantity(_bandwidth, 'Hz')

        # Apply robust heuristic based on beam sizes for the used robust values.
        if reprBW_mode in ['nbin', 'repr_spw']:
            hm_robust, hm_robust_score, beamRatio_0p0, beamRatio_0p5, beamRatio_1p0, beamRatio_2p0 = \
                imageprecheck_heuristics.compare_beams( \
                    beams[(0.0, str(default_uvtaper), 'repBW')], \
                    beams[(0.5, str(default_uvtaper), 'repBW')], \
                    beams[(1.0, str(default_uvtaper), 'repBW')], \
                    beams[(2.0, str(default_uvtaper), 'repBW')], \
                    minAcceptableAngResolution, \
                    maxAcceptableAngResolution, \
                    maxAllowedBeamAxialRatio)
        else:
            hm_robust, hm_robust_score, beamRatio_0p0, beamRatio_0p5, beamRatio_1p0, beamRatio_2p0 = \
                imageprecheck_heuristics.compare_beams( \
                    beams[(0.0, str(default_uvtaper), 'aggBW')], \
                    beams[(0.5, str(default_uvtaper), 'aggBW')], \
                    beams[(1.0, str(default_uvtaper), 'aggBW')], \
                    beams[(2.0, str(default_uvtaper), 'aggBW')], \
                    minAcceptableAngResolution, \
                    maxAcceptableAngResolution, \
                    maxAllowedBeamAxialRatio)

        # Save beam ratios for weblog
        beamRatios = { \
            (0.0, str(default_uvtaper)): beamRatio_0p0,
            (0.5, str(default_uvtaper)): beamRatio_0p5,
            (1.0, str(default_uvtaper)): beamRatio_1p0,
            (2.0, str(default_uvtaper)): beamRatio_2p0
            }

        # Determine non-default UV taper value if the best robust is 2.0 and the user requested resolution parameter
        # (desired_angular_resolution) is set. (PIPE-708)
        #
        # Compute uvtaper for representative targets and also if representative target cannot be determined
        # (real_repr_target = False) for representative targets and if user set angular resolution goal.
        #
        # Note that uvtaper is not computed for the ACA (7m) array, because robust of 2.0 is not in the checked range
        # (see robust_values_to_check).
        if hm_robust == 2.0 and cqa.getvalue(userAngResolution)[0] != 0.0:
            # Calculate the length of the 190th baseline, used to set the upper limit on uvtaper. See PIPE-1104.
            length_of_190th_baseline = image_heuristics.calc_length_of_nth_baseline(190)
            reprBW_mode_string = ['repBW' if reprBW_mode in ['nbin', 'repr_spw'] else 'aggBW']
            # self.calc_uvtaper method is only available in hifas_imageprecheck
            try:
                hm_uvtaper = self.calc_uvtaper(beam_natural=beams[(2.0, str(default_uvtaper), reprBW_mode_string[0])],
                                               beam_user=user_desired_beam,
                                               tapering_limit=length_of_190th_baseline, repr_freq=repr_freq)
            except:
                hm_uvtaper = []
            if hm_uvtaper != []:
                # Add sensitivity entries with actual tapering
                beams[(hm_robust, str(hm_uvtaper), 'repBW')], known_synthesized_beams = image_heuristics.synthesized_beam(
                    [(repr_field, 'TARGET')], str(repr_spw), robust=hm_robust, uvtaper=hm_uvtaper,
                    known_beams=known_synthesized_beams, force_calc=calcsb, parallel=parallel, shift=True)

                # If the beam is invalid, error and return.
                if beams[(hm_robust, str(hm_uvtaper), 'repBW')] == 'invalid':
                    LOG.error('Beam for uvtaper repBW is invalid. Cannot continue.')
                    return ImagePreCheckResults(error=True, error_msg='Invalid beam')

                cells[(hm_robust, str(hm_uvtaper), 'repBW')] = image_heuristics.cell(beams[(hm_robust, str(hm_uvtaper), 'repBW')])
                imsizes[(hm_robust, str(hm_uvtaper), 'repBW')] = image_heuristics.imsize(field_ids, cells[(hm_robust, str(hm_uvtaper), 'repBW')], primary_beam_size, centreonly=False, intent='TARGET')
                if reprBW_mode in ['nbin', 'repr_spw']:
                    try:
                        sensitivity, eff_ch_bw, sens_bw, known_per_spw_cont_sensitivities_all_chan = \
                            image_heuristics.calc_sensitivities(inputs.vis, repr_field, 'TARGET', str(repr_spw), nbin, {}, 'cube', gridder, cells[(hm_robust, str(hm_uvtaper), 'repBW')], imsizes[(hm_robust, str(hm_uvtaper), 'repBW')], 'briggs', hm_robust, hm_uvtaper, True, known_per_spw_cont_sensitivities_all_chan, calcsb)
                        sensitivities.append(Sensitivity(
                            array=array,
                            intent='TARGET',
                            field=repr_field,
                            spw=str(repr_spw),
                            is_representative=True,
                            bandwidth=cqa.quantity(sens_bw, 'Hz'),
                            bwmode='repBW',
                            beam=beams[(hm_robust, str(hm_uvtaper), 'repBW')],
                            cell=[cqa.convert(cells[(hm_robust, str(hm_uvtaper), 'repBW')][0], 'arcsec'),
                                  cqa.convert(cells[(hm_robust, str(hm_uvtaper), 'repBW')][0], 'arcsec')],
                            robust=hm_robust,
                            uvtaper=hm_uvtaper,
                            sensitivity=cqa.quantity(sensitivity, 'Jy/beam')))
                    except Exception as e:
                        sensitivities.append(Sensitivity(
                            array=array,
                            intent='TARGET',
                            field=repr_field,
                            spw=str(repr_spw),
                            is_representative=True,
                            bandwidth=cqa.quantity(0.0, 'Hz'),
                            bwmode='repBW',
                            beam=beams[(hm_robust, str(hm_uvtaper), 'repBW')],
                            cell=['0.0 arcsec', '0.0 arcsec'],
                            robust=robust,
                            uvtaper=hm_uvtaper,
                            sensitivity=cqa.quantity(0.0, 'Jy/beam')))

                beams[(hm_robust, str(hm_uvtaper), 'aggBW')], known_synthesized_beams = image_heuristics.synthesized_beam(
                    [(repr_field, 'TARGET')], cont_spw, robust=hm_robust, uvtaper=hm_uvtaper,
                    known_beams=known_synthesized_beams, force_calc=calcsb, parallel=parallel, shift=True)

                # If the beam is invalid, error and return.
                if beams[(hm_robust, str(hm_uvtaper), 'aggBW')] == 'invalid':
                    LOG.error('Beam for uvtaper aggBW is invalid. Cannot continue.')
                    return ImagePreCheckResults(error=True, error_msg='Invalid beam')

                cells[(hm_robust, str(hm_uvtaper), 'aggBW')] = image_heuristics.cell(beams[(hm_robust, str(hm_uvtaper), 'aggBW')])
                imsizes[(hm_robust, str(hm_uvtaper), 'aggBW')] = image_heuristics.imsize(field_ids, cells[(hm_robust, str(hm_uvtaper), 'aggBW')], primary_beam_size, centreonly=False, intent='TARGET')
                try:
                    sensitivity, eff_ch_bw, sens_bw, known_per_spw_cont_sensitivities_all_chan = \
                        image_heuristics.calc_sensitivities(inputs.vis, repr_field, 'TARGET', cont_spw, -1, {}, 'cont', gridder, cells[(hm_robust, str(hm_uvtaper), 'aggBW')], imsizes[(hm_robust, str(hm_uvtaper), 'aggBW')], 'briggs', hm_robust, hm_uvtaper, True, known_per_spw_cont_sensitivities_all_chan, calcsb)
                    if scale_aggBW_to_repBW and cont_sens_bw_mode == 'repBW':
                        # Handle scaling to repSPW_BW < repBW <= 0.9 * aggBW case
                        _bandwidth = repr_target[2]
                        _sensitivity = cqa.mul(cqa.quantity(sensitivity, 'Jy/beam'), cqa.sqrt(cqa.div(cqa.quantity(sens_bw, 'Hz'), repr_target[2])))
                    else:
                        _bandwidth = cqa.quantity(min(sens_bw, num_cont_spw * 1.875e9), 'Hz')
                        _sensitivity = cqa.quantity(sensitivity, 'Jy/beam')

                    for cont_sens_bw_mode in cont_sens_bw_modes:
                        sensitivities.append(Sensitivity(
                            array=array,
                            intent='TARGET',
                            field=repr_field,
                            spw=str(repr_spw),
                            is_representative=True,
                            bandwidth=_bandwidth,
                            bwmode=cont_sens_bw_mode,
                            beam=beams[(hm_robust, str(hm_uvtaper), 'aggBW')],
                            cell=[cqa.convert(cells[(hm_robust, str(hm_uvtaper), 'aggBW')][0], 'arcsec'),
                                  cqa.convert(cells[(hm_robust, str(hm_uvtaper), 'aggBW')][0], 'arcsec')],
                            robust=hm_robust,
                            uvtaper=hm_uvtaper,
                            sensitivity=_sensitivity))
                except:
                    for _ in cont_sens_bw_modes:
                        sensitivities.append(Sensitivity(
                            array=array,
                            intent='TARGET',
                            field=repr_field,
                            spw=str(repr_spw),
                            is_representative=True,
                            bandwidth=cqa.quantity(0.0, 'Hz'),
                            bwmode='repBW',
                            beam=beams[(hm_robust, str(hm_uvtaper), 'aggBW')],
                            cell=['0.0 arcsec', '0.0 arcsec'],
                            robust=robust,
                            uvtaper=hm_uvtaper,
                            sensitivity=cqa.quantity(0.0, 'Jy/beam')))

                # Update beamRatios
                if reprBW_mode in ['nbin', 'repr_spw']:
                    beamRatios[(hm_robust, str(hm_uvtaper))] = cqa.tos(cqa.div(beams[(hm_robust, str(hm_uvtaper),
                                                                                      'repBW')]['major'],
                                                                               beams[(hm_robust, str(hm_uvtaper),
                                                                                      'repBW')]['minor']),
                                                                       2)
                else:
                    beamRatios[(hm_robust, str(hm_uvtaper))] = cqa.tos(cqa.div(beams[(hm_robust, str(hm_uvtaper),
                                                                                      'aggBW')]['major'],
                                                                               beams[(hm_robust, str(hm_uvtaper),
                                                                                      'aggBW')]['minor']),
                                                                       2)

        else:
            hm_uvtaper = default_uvtaper

        return ImagePreCheckResults(
            real_repr_target,
            repr_target,
            repr_source,
            repr_spw,
            reprBW_mode,
            nbin,
            minAcceptableAngResolution=pi_minAcceptableAngResolution,
            maxAcceptableAngResolution=pi_maxAcceptableAngResolution,
            maxAllowedBeamAxialRatio=pi_maxAllowedBeamAxialRatio,
            user_minAcceptableAngResolution=user_minAcceptableAngResolution,
            user_maxAcceptableAngResolution=user_maxAcceptableAngResolution,
            user_maxAllowedBeamAxialRatio=user_maxAllowedBeamAxialRatio,
            sensitivityGoal=sensitivityGoal,
            hm_robust=hm_robust,
            hm_uvtaper=hm_uvtaper,
            sensitivities=sensitivities,
            sensitivity_bandwidth=sensitivity_bandwidth,
            score=hm_robust_score,
            single_continuum=single_continuum,
            per_spw_cont_sensitivities_all_chan=known_per_spw_cont_sensitivities_all_chan,
            synthesized_beams=known_synthesized_beams,
            beamRatios=beamRatios
        )

    def analyse(self, results):
        return super().analyse(results)

    def calc_uvtaper(self, beam_natural=None,  beam_user=None, tapering_limit=None, repr_freq=None):
        """
        This code will take a given beam and a desired beam size and calculate the necessary
        UV-tapering parameters needed for tclean to recreate that beam.

        UV-tapering parameter larger than the 80 percentile baseline is not allowed.

        :param beam_natural: natural beam, dictionary with major, minor and positionangle keywords
        :param beam_user: desired beam, dictionary with major, minor and positionangle keywords
        :param tapering_limit: 190th baseline in meters. uvtaper larger than this baseline is not allowed
        :param repr_freq: representative frequency, dictionary with unit and value keywords.
        :return: uv_taper needed to recreate user_beam in tclean
        """
        if beam_natural is None:
            return []
        if beam_user is None:
            return []
        if tapering_limit is None:
            return []
        if repr_freq is None:
            return []

        # Determine uvtaper based on equations from Ryan Loomis,
        # https://open-confluence.nrao.edu/display/NAASC/Data+Processing%3A+Imaging+Tips
        # See PIPE-704.
        cqa = casa_tools.quanta

        bmajor = 1.0 / cqa.getvalue(cqa.convert(beam_natural['major'], 'arcsec'))
        bminor = 1.0 / cqa.getvalue(cqa.convert(beam_natural['minor'], 'arcsec'))

        des_bmajor = 1.0 / cqa.getvalue(cqa.convert(beam_user['major'], 'arcsec'))
        des_bminor = 1.0 / cqa.getvalue(cqa.convert(beam_user['minor'], 'arcsec'))

        if (des_bmajor > bmajor) or (des_bminor > bminor):
            LOG.warning('uvtaper cannot be calculated for beam_user (%.2farcsec) larger than beam_natural (%.2farcsec)' % (
                1.0 / des_bmajor, 1.0 / bmajor))
            return []

        tap_bmajor = 1.0 / (bmajor * des_bmajor / (math.sqrt(bmajor ** 2 - des_bmajor ** 2)))
        tap_bminor = 1.0 / (bminor * des_bminor / (math.sqrt(bminor ** 2 - des_bminor ** 2)))

        # Assume symmetric beam
        tap_angle = math.sqrt( (tap_bmajor ** 2 + tap_bminor ** 2) / 2.0 )

        # Convert angle to baseline
        ARCSEC_PER_RAD = 206264.80624709636
        uvtaper_value = ARCSEC_PER_RAD / tap_angle
        LOG.info('uvtaper needed to achive user specified angular resolution is %.2fklambda' %
                 utils.round_half_up(uvtaper_value / 1000., 2))

        # Determine maximum allowed uvtaper
        # PIPE-1104: Limit such that the image includes the baselines from at least 20 antennas.
        # Limit should be set to: (N*(N-1)/2)=the length of the 190th baseline.
        uvtaper_limit = tapering_limit / cqa.getvalue(cqa.convert(cqa.constants('c'), 'm/s'))[0] * \
                        cqa.getvalue(cqa.convert(repr_freq, 'Hz'))[0]
        # Limit uvtaper
        if uvtaper_value < uvtaper_limit:
            uvtaper_value = uvtaper_limit
            LOG.warning('uvtaper is smaller than allowed limit of %.2fklambda, the length of the 190th baseline, using the limit value' %
                        utils.round_half_up(uvtaper_limit / 1000., 2))
        return ['%.2fklambda' % utils.round_half_up(uvtaper_value / 1000., 2)]
