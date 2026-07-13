import math
import operator
import copy

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
from pipeline.hif.tasks.makeimlist import makeimlist

LOG = infrastructure.get_logger(__name__)


class CheckProductSizeHeuristics:
    def __init__(self, inputs):
        self.inputs = inputs
        self.context = inputs.context

    def calculate_sizes(self, imlist):
        cubesizes = {}
        productsizes = {}
        total_productsize = 0.0
        ref_ms = self.context.observing_run.measurement_sets[0]
        for target in imlist:
            nx, ny = target['imsize']

            if target['nbin'] != -1:
                nbin = target['nbin']
            else:
                nbin = 1

            if target['specmode'] == 'cube':
                real_spw = self.context.observing_run.virtual2real_spw_id(int(target['spw']), ref_ms)
                nchan = ref_ms.get_spectral_window(real_spw).num_channels
                cubesize = 4. * nx * ny * nchan / nbin / 1e9
            # Handle the 'cont' specmode case
            else:
                nchan = 1
                cubesize = 0.0

            mfssize = 4. * nx * ny / 1e9 # Should include nterms, though overall size is dominated by cube mode which is currently always nterms=1

            if self.context.processing_intents is not None and 'INTERFEROMETRY_FULL_POL_CUBE_IMAGING' in self.context.processing_intents:
                # Original I plus IQUV products
                cubesize = 5 * cubesize
                mfssize = 5 * mfssize

            # this will assign the cubesize dict (keyed by spw) to
            # the max size for any target that uses this spw
            if cubesizes.get(target['spw']) is not None:
                cubesizes[target['spw']] = max(cubesizes[target['spw']],cubesize)
            else:
                cubesizes[target['spw']] = cubesize
            productsize = 2.0 * (mfssize + cubesize)
            # Since CAS-11363 this process technically only returns product sizes (keyed by spw)
            # for the last target. The underlying assumption is that irrespective of the target
            # all cubes for a given spw are the ~same size
            productsizes[target['spw']] = productsize
            total_productsize += productsize
            LOG.info('Cube size for Field %s SPW %s nchan %d nbin %d imsize %d x %d is %.3g GB' % (target['field'], target['spw'], nchan, nbin, nx, ny, cubesize))

        return cubesizes, max(cubesizes.values()), productsizes, total_productsize

    def mitigate_sizes(self):

        known_synthesized_beams = self.context.synthesized_beams

        # Initialize mitigation parameter dictionary
        # Possible keys:
        # 'nbins', 'hm_imsize', 'hm_cell', 'field'
        size_mitigation_parameters = {}

        # Create makeimlist inputs
        makeimlist_inputs = makeimlist.MakeImListInputs(self.context)
        makeimlist_inputs.intent = 'TARGET'
        makeimlist_inputs.specmode = 'cube'
        makeimlist_inputs.clearlist = True
        makeimlist_inputs.calcsb = self.inputs.calcsb

        # Create makeimlist task for size calculations
        makeimlist_task = makeimlist.MakeImList(makeimlist_inputs)

        # Get default target setup
        makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
        makeimlist_result = makeimlist_task.prepare()
        known_synthesized_beams = makeimlist_result.synthesized_beams
        imlist = makeimlist_result.targets

        # Extract some information for later
        #
        # Sort fields to get consistent mitigation results.
        fields = sorted({i['field'] for i in imlist})
        nfields = len(fields)
        spws = list({i['spw'] for i in imlist})
        ref_ms = self.context.observing_run.measurement_sets[0]
        real_spws = [self.context.observing_run.virtual2real_spw_id(int(spw), ref_ms) for spw in spws]
        nchans = dict([(spw, ref_ms.get_spectral_window(real_spw).num_channels) for spw, real_spw in zip(spws, real_spws)])
        frequencies = dict([(spw, float(ref_ms.get_spectral_window(real_spw).centre_frequency.convert_to(measures.FrequencyUnits.HERTZ).value)) for spw, real_spw in zip(spws, real_spws)])
        ch_width_ratios = dict([(spw, \
            float(ref_ms.get_spectral_window(real_spw).channels[0].effective_bw.convert_to(measures.FrequencyUnits.HERTZ).value) / \
            float(ref_ms.get_spectral_window(real_spw).channels[0].getWidth().convert_to(measures.FrequencyUnits.HERTZ).value)) \
            for spw, real_spw in zip(spws, real_spws)])

        if nfields == 0:
            LOG.warning("Cannot determine any default specmode='cube' imaging targets")
            long_short_msg = {'longmsg': "Cannot determine any default specmode='cube' imaging targets",
                              'shortmsg': 'Cannot determine targets'}
            return {}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, True, long_short_msg, known_synthesized_beams

        # Get representative target information
        repr_target, \
        repr_source, \
        repr_spw, \
        repr_freq, \
        reprBW_mode, \
        real_repr_target, \
        minAcceptableAngResolution, \
        maxAcceptableAngResolution, \
        maxAllowedBeamAxialRatio, \
        sensitivityGoal = \
            imlist[0]['heuristics'].representative_target()

        # Make sure that the representative source is the first list item.
        fields = utils.place_repr_source_first(fields, repr_source)

        # Get original maximum cube and product sizes
        cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
        original_maxcubesize = maxcubesize
        original_productsize = total_productsize
        # Requested image size
        original_imsize = imlist[0]['imsize']
        mitigated_imsize = original_imsize
        # print(original_imsize) # testing # note could form an output dict with metric scores already with mitigation levels
        LOG.info('Default imaging leads to a maximum cube size of %.4f GB and a product size of %.4f GB' % (maxcubesize, total_productsize))
        LOG.info('Allowed maximum cube size: %s GB. Allowed cube size limit: %s GB. Allowed maximum product size: %s GB.' % (self.inputs.maxcubesize, self.inputs.maxcubelimit, self.inputs.maxproductsize))

        # Step 1 - testing maximum cube size
        # If too large, try to mitigate via channel binning
        if (self.inputs.maxcubesize != -1.0) and (maxcubesize > self.inputs.maxcubesize):
            LOG.info('Maximum cube size is too large. Trying nbin mitigation.')
            nbins = []
            nbin_mitigation = False
            for spw, nchan in nchans.items():
                if (nchan in (7680, 3840)) or (nchan in (1920, 960, 480) and utils.equal_to_n_digits(ch_width_ratios[spw], 2.667, 4)):
                    LOG.info('Size mitigation: Setting nbin for SpW %s to 2.' % (spw))
                    nbins.append('%s:2' % (spw))
                    nbin_mitigation = True
                else:
                    nbins.append('%s:1' % (spw))
            if nbin_mitigation:
                size_mitigation_parameters['nbins'] = ','.join(nbins)

                # Recalculate sizes
                makeimlist_inputs.nbins = size_mitigation_parameters['nbins']
                makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                makeimlist_result = makeimlist_task.prepare()
                known_synthesized_beams = makeimlist_result.synthesized_beams
                imlist = makeimlist_result.targets
                cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
                mitigated_imsize = imlist[0]['imsize']
                LOG.info('nbin mitigation leads to a maximum cube size of %.4f GB' % (maxcubesize))

        # If still too large, try changing the FoV (in makeimlist this is applied to single fields only)
        PB_limit = 0.2
        if (self.inputs.maxcubesize != -1.0) and (maxcubesize > self.inputs.maxcubesize):
            LOG.info('Maximum cube size is still too large. Trying FoV mitigation.')

            # Calculate PB level at which the largest cube size of all targets
            # is equal to the maximum allowed cube size.
            PB_mitigation = math.exp(-math.log(2.0) * 2.2064 * self.inputs.maxcubesize / maxcubesize / 1.01)
            # Cap at PB=0.7
            PB_mitigation = min(PB_mitigation, 0.7)
            # Cap at PB=0.2
            PB_mitigation = max(PB_mitigation, 0.2)
            # Round to 2 significant digits
            PB_mitigation = utils.round_half_up(PB_mitigation, 2)

            PB_limit = PB_mitigation

            if PB_limit != 0.2:
                LOG.info('Size mitigation: Setting hm_imsize to %.2gpb' % (PB_mitigation))
                size_mitigation_parameters['hm_imsize'] = '%.2gpb' % (PB_mitigation)

                # Recalculate sizes
                makeimlist_inputs.hm_imsize = size_mitigation_parameters['hm_imsize']
                makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                makeimlist_result = makeimlist_task.prepare()
                known_synthesized_beams = makeimlist_result.synthesized_beams
                imlist = makeimlist_result.targets
                cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
                mitigated_imsize = imlist[0]['imsize']
                LOG.info('hm_imsize mitigation leads to a maximum cube size of %.4f GB' % (maxcubesize))

        # If still too large, try changing pixperbeam setting
        if (self.inputs.maxcubesize != -1.0) and (maxcubesize > self.inputs.maxcubesize):
            LOG.info('Maximum cube size is still too large. Trying cell size mitigation.')
            
            if 'robust' in self.context.imaging_parameters:
                robust = self.context.imaging_parameters['robust']
            else:
                robust = None
            if robust == 2.0:
                # Special case to avoid undersampling the beam (PIPE-107)
                size_mitigation_parameters['hm_cell'] = '3.25ppb'
            else:
                size_mitigation_parameters['hm_cell'] = '3ppb'
            LOG.info('Size mitigation: Setting hm_cell to %s' % (size_mitigation_parameters['hm_cell']))

            # Recalculate sizes
            makeimlist_inputs.hm_cell = size_mitigation_parameters['hm_cell']
            makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
            makeimlist_result = makeimlist_task.prepare()
            known_synthesized_beams = makeimlist_result.synthesized_beams
            imlist = makeimlist_result.targets
            cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
            mitigated_imsize = imlist[0]['imsize']
            LOG.info('hm_cell mitigation leads to a maximum cube size of %.4f GB' % (maxcubesize))


        # PIPE-3127
        # If still too large, final check and if no mitigation possible then warn - SpW filtering will occur later, but do not error
        if (self.inputs.maxcubesize != -1.0) and (maxcubesize > self.inputs.maxcubesize):
            LOG.info('Maximum cube size cannot be mitigated. Remaining factor with the maxcubesize is: %.4f.'%(maxcubesize / self.inputs.maxcubesize))
            LOG.info('SpW filtering will occur if maximum cube size is greater than limit of %s GB.' %(self.inputs.maxcubelimit))

            
        # Step 2 mitigation for total product size
        # If product size too large, try reducing number of fields / targets
        if (self.inputs.maxproductsize != -1.0) and (total_productsize > self.inputs.maxproductsize) and (nfields > 1):
            LOG.info('Product size with multiple targets is too large. Trying field mitigation.')
            
            nfields = int(self.inputs.maxproductsize / (total_productsize / len(fields)))
            if nfields == 0:
                nfields = 1

            # Truncate the field list. The representative source is always
            # included since it is the first list item.
            mitigated_fields = fields[:nfields]

            size_mitigation_parameters['field'] = ','.join(mitigated_fields)

            LOG.info('Size mitigation: Setting field to %s' % (size_mitigation_parameters['field']))

            # Recalculate sizes
            makeimlist_inputs.field = size_mitigation_parameters['field']
            makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
            makeimlist_result = makeimlist_task.prepare()
            known_synthesized_beams = makeimlist_result.synthesized_beams
            imlist = makeimlist_result.targets
            cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
            LOG.info('field / target mitigation leads to product size of %.4f GB' % (total_productsize))

        # If cube size is OK, but product size with single target is still too large, try mitigating further with nbin, FoV, and cell size
        if (nfields == 1) and (self.inputs.maxcubesize != -1.0) and (maxcubesize < self.inputs.maxcubesize):
            if (self.inputs.maxproductsize != -1.0) and (total_productsize > self.inputs.maxproductsize):
                LOG.info('Product size with single target is too large. Trying nbin mitigation.')

                nbins = []
                nbin_mitigation = False
                for spw, nchan in nchans.items():
                    if (nchan in (7680, 3840)) or (nchan in (1920, 960, 480) and utils.equal_to_n_digits(ch_width_ratios[spw], 2.667, 4)):
                        LOG.info('Size mitigation: Setting nbin for SPW %s to 2.' % (spw))
                        nbins.append('%s:2' % (spw))
                        nbin_mitigation = True
                    else:
                        nbins.append('%s:1' % (spw))

                if nbin_mitigation:
                    size_mitigation_parameters['nbins'] = ','.join(nbins)

                    # Recalculate sizes
                    makeimlist_inputs.nbins = size_mitigation_parameters['nbins']
                    makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                    makeimlist_result = makeimlist_task.prepare()
                    known_synthesized_beams = makeimlist_result.synthesized_beams
                    imlist = makeimlist_result.targets
                    cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
                    LOG.info('nbin mitigation leads to a maximum cube size of %.4f GB' % (maxcubesize))
                    LOG.info('nbin mitigation leads to product size of %.4f GB' % (total_productsize))

            if (self.inputs.maxproductsize != -1.0) and (total_productsize > self.inputs.maxproductsize):
                LOG.info('Product size with single target is still too large. Trying FoV mitigation.')

                # Calculate PB level at which the largest cube size of all targets
                # is equal to the maximum allowed cube size.
                PB_mitigation = math.exp(-math.log(2.0) * 2.2064 * self.inputs.maxcubesize / maxcubesize / 1.01)
                # Cap at PB=0.7
                PB_mitigation = min(PB_mitigation, 0.7)
                # Cap at PB=<current PB_limit from earlier mitigation>
                PB_mitigation = max(PB_mitigation, PB_limit)
                # Round to 2 significant digits
                PB_mitigation = utils.round_half_up(PB_mitigation, 2)

                if PB_mitigation != 0.2:
                    LOG.info('Size mitigation: Setting hm_imsize to %.2gpb' % (PB_mitigation))
                    size_mitigation_parameters['hm_imsize'] = '%.2gpb' % (PB_mitigation)

                    # Recalculate sizes
                    makeimlist_inputs.hm_imsize = size_mitigation_parameters['hm_imsize']
                    makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                    makeimlist_result = makeimlist_task.prepare()
                    known_synthesized_beams = makeimlist_result.synthesized_beams
                    imlist = makeimlist_result.targets
                    cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
                    LOG.info('hm_imsize mitigation leads to a maximum cube size of %.4f GB' % (maxcubesize))
                    LOG.info('hm_imsize mitigation leads to product size of %.4f GB' % (total_productsize))

            if (self.inputs.maxproductsize != -1.0) and (total_productsize > self.inputs.maxproductsize):
                LOG.info('Product size with single target is still too large. Trying cell size mitigation.')

                if 'robust' in self.context.imaging_parameters:
                    robust = self.context.imaging_parameters['robust']
                else:
                    robust = None
                if robust == 2.0:
                    # Special case to avoid undersampling the beam (PIPE-107)
                    size_mitigation_parameters['hm_cell'] = '3.25ppb'
                else:
                    size_mitigation_parameters['hm_cell'] = '3ppb'
                LOG.info('Size mitigation: Setting hm_cell to %s' % (size_mitigation_parameters['hm_cell']))

                # Recalculate sizes
                makeimlist_inputs.hm_cell = size_mitigation_parameters['hm_cell']
                makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                makeimlist_result = makeimlist_task.prepare()
                known_synthesized_beams = makeimlist_result.synthesized_beams
                imlist = makeimlist_result.targets
                cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
                LOG.info('hm_cell mitigation leads to a maximum cube size of %.4f GB' % (maxcubesize))
                LOG.info('hm_cell mitigation leads to product size of %.4f GB' % (total_productsize))

        # end of step 2 - make a warning if the total products are too large - spw filtering will be done later
        if (self.inputs.maxproductsize != -1.0) and (total_productsize > self.inputs.maxproductsize):
            LOG.info('Product size could not be mitigated. Remaining factor: %.4f. SpW filtering will occur to reduce the total product size.' % (total_productsize / self.inputs.maxproductsize))

        # Save cube mitigated product size for logs
        cube_mitigated_productsize = total_productsize
        
        # Step 3
        # First this creates a list of all the SpW, there is a single spw list irrespective of the number of targets
        # The oversize decision to make each as oversize comes from the >0.5*maxcubelimit

        # Next, spws are filtered based on EITHER clauses:
        # if there is are any spw triggering the "oversized" criteria of cubes larger than 0.5 * maxcubelimit
        # or total size > maxproduct size, i.e. the continuation of the STEP 2 workflow
        
        # set the large cube mitigation to False to separate this from general SpW filtering
        large_cube_mitigation = False
        if (self.inputs.maxcubelimit != -1) or (self.inputs.maxproductsize != -1.0):
            # prepare dictionaries to hold oversize and overlimit cubesize (PIPE-3127) SpW lists
            LOG.info(' *** These are the initial spws listed: < %s >'%(','.join(spws)))
            spw_oversizes = dict([(i, 0) for i in spws])
            spw_overlimit = dict([(i, 0) for i in spws])
            
            # now loop all targets in the imlist and their spws
            for target in imlist:
                # if any cubes are over the 0.5 limit then set these to be oversize
                # any target can cause a spw to be oversize even if other targets of that spw are not oversized
                if (cubesizes[target['spw']] > 0.5 * self.inputs.maxcubelimit) and (self.inputs.maxcubelimit != -1):
                    spw_oversizes[target['spw']] += 1  
                # if any cubes are over the maxcubelimit then set them to be overlimit
                if (cubesizes[target['spw']] > self.inputs.maxcubelimit) and (self.inputs.maxcubelimit != -1):
                    spw_overlimit[target['spw']] += 1  


            # logic clause for the spw filtering loops
            # - spw are oversize
            # - total products were too big
            # - cubesize > maxcubelimit
            if ([n != 0 for n in spw_oversizes.values()].count(True) > 1) or \
               ((total_productsize > self.inputs.maxproductsize) and (self.inputs.maxproductsize != -1)) or \
               ((maxcubesize > self.inputs.maxcubelimit) and (self.inputs.maxcubelimit != -1)):
                # create a separate list for spw that are over the maxcubelimit:
                overlimit_spws = [spw for spw, n in spw_overlimit.items() if n>0]
                if overlimit_spws != []:
                    LOG.info('*** These spws are over the maxcubelimit:<  %s  >'%(',').join(overlimit_spws))
                # PIPE-3127 move the main step 1 exit clause here when checking if the representative SpW is over this limit as we will not continue
                if str(repr_spw) in overlimit_spws:
                    LOG.error('Maximum cube size cannot be mitigated. Remaining factor with the maxcubesize is: %.4f' % (maxcubesize / self.inputs.maxcubesize))
                    LOG.error('The representative SpW (%s) cube size is larger than the limit of %s'%(repr_spw,self.inputs.maxcubelimit))
                    return size_mitigation_parameters, \
                       original_maxcubesize, original_productsize, \
                       cube_mitigated_productsize, \
                       maxcubesize, total_productsize, \
                       original_imsize, mitigated_imsize, \
                       True, \
                       {'longmsg': 'Cube size could not be mitigated. Remaining factor: %.4f and the representative SpW cube size is larger than the limit of %s GB.' % (maxcubesize / self.inputs.maxcubesize, self.inputs.maxcubelimit), \
                        'shortmsg': 'Cube size could not be mitigated'}, \
                       known_synthesized_beams                    

                # if the maxcubelimit error did not trigger we can continue the spw filtering as below
                # create a specific oversize spw list that explicitly excludes any overlimit spws that exceeded the maxcubelimit
                oversize_spws = [spw for spw, n in spw_oversizes.items() if n>0 and spw not in overlimit_spws]

                # Imaging will make at least one large cube if there are any
                # if the repSpW is an oversize cube, it is added, else the first index spw of the list                
                if oversize_spws != []:
                    LOG.info('*** These spws are over the oversize criteria :<  %s  >'%(',').join(oversize_spws))                
                    large_cube_mitigation=True # to trigger specifically the large cube spw mitigation message
                    LOG.info('At least one cube size exceeded the large cube limit. Only one large SpW will be imaged.')                                        
                    if str(repr_spw) in oversize_spws:
                        large_cube_spw = str(repr_spw)
                    else:
                        large_cube_spw = oversize_spws[0]
                    mitigated_spws = [large_cube_spw]
                    mitigated_productsize = productsizes[large_cube_spw]
                # at this else we have no oversized cubes, thus build the SpW list starting with the representative SpW onwards
                else:
                    mitigated_spws = []
                    mitigated_productsize = 0.0
                # Add at least the representative spw if it is among the small cubes.
                if str(repr_spw) not in oversize_spws:
                    mitigated_spws.append(str(repr_spw))
                    mitigated_productsize += productsizes[str(repr_spw)]
                    
                # Add other small cubes regardless of which initial clause got to this point
                # i.e. oversize cube, total productsize, or maxcubesize
                other_small_cube_spws = [spw for spw, n in spw_oversizes.items() if n==0 and spw != str(repr_spw)]
                small_cube_frequencies = [frequencies[spw] for spw in other_small_cube_spws]
                small_cube_productsizes = [productsizes[spw] for spw in other_small_cube_spws]
                small_cube_info = list(zip(other_small_cube_spws, small_cube_frequencies, small_cube_productsizes))
                # Sort spw list by size and frequency
                small_cube_info = sorted(small_cube_info, key=operator.itemgetter(2, 1))
                for small_cube_spw, small_cube_frequency, small_cube_productsize in small_cube_info:
                    if (mitigated_productsize + small_cube_productsize <= self.inputs.maxproductsize) or (self.inputs.maxproductsize == -1):
                        mitigated_spws.append(small_cube_spw)
                        mitigated_productsize += small_cube_productsize
                    else:
                        break
                # final mitigated spw list to propagate
                size_mitigation_parameters['spw'] = ','.join(map(str, sorted(mitigated_spws)))
                LOG.info('Size mitigation: Setting (cube) spw to %s' % (size_mitigation_parameters['spw']))

                # Recalculate sizes
                makeimlist_inputs.spw = size_mitigation_parameters['spw']
                makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                # Keep previous imsize and cell which would change if the spw list is different (due to freq.)
                hm_imsize_orig = makeimlist_inputs.hm_imsize
                makeimlist_inputs.hm_imsize = makeimlist_result.targets[0]['imsize']
                hm_cell_orig = makeimlist_inputs.hm_cell
                makeimlist_inputs.hm_cell = makeimlist_result.targets[0]['cell']
                makeimlist_result = makeimlist_task.prepare()
                known_synthesized_beams = makeimlist_result.synthesized_beams
                # Restore previous settings
                makeimlist_inputs.hm_imsize = hm_imsize_orig
                makeimlist_inputs.hm_cell = hm_cell_orig
                imlist = makeimlist_result.targets
                cubesizes, maxcubesize, productsizes, total_productsize = self.calculate_sizes(imlist)
                # Save cube mitigated product size for logs
                cube_mitigated_productsize = total_productsize                
                LOG.info('SpW mitigation leads to a maximum cube size of %.4f GB' % (maxcubesize))                
                LOG.info('SpW mitigation leads to product size of %.4f GB' % (total_productsize))

        # Final logging statements
        # Step 1 already exited above if rep SpW exceeded the limit, but we can still have repr spw as a large cube (PIPE-3127)
        if (self.inputs.maxcubesize != -1.0) and (maxcubesize > self.inputs.maxcubesize):
            if maxcubesize < self.inputs.maxcubelimit:
                LOG.info('Maximum cube size cannot be mitigated. Remaining factor with the maxcubesize is: %.4f.'%(maxcubesize / self.inputs.maxcubesize))
                LOG.info('But the maximum cube size is smaller than limit of %s GB.' % (self.inputs.maxcubelimit))
        # Step 2 cause on total product size to exit                      
        if (self.inputs.maxproductsize != -1.0) and (total_productsize > self.inputs.maxproductsize):
            LOG.error('Product size cannot be mitigated. Remaining factor: %.4f.' % (total_productsize / self.inputs.maxproductsize / nfields))
            return size_mitigation_parameters, \
                   original_maxcubesize, original_productsize, \
                   cube_mitigated_productsize, \
                   maxcubesize, total_productsize, \
                   original_imsize, mitigated_imsize, \
                   True, \
                   {'longmsg': 'Product size could not be mitigated. Remaining factor: %.4f.' % (total_productsize / self.inputs.maxproductsize / nfields), \
                    'shortmsg': 'Product size could not be mitigated'}, \
                   known_synthesized_beams

        # Check for case with many targets which will cause long run times in spite
        # of any mitigation.
        max_num_sciencetargets = 30
        if (nfields > max_num_sciencetargets) and (sum(nchans.values()) > 960):
            LOG.warning('The number of science targets is > 30 and the total number of spectral channels across all science spws > 960. '
                        'The imaging pipeline will take substantial time to run on this MOUS.')

        if size_mitigation_parameters != {}:
            return size_mitigation_parameters, \
                   original_maxcubesize, original_productsize, \
                   cube_mitigated_productsize, \
                   maxcubesize, total_productsize, \
                   original_imsize, mitigated_imsize, \
                   False, \
                   {'longmsg': 'Size had to be mitigated (%s)%s' % (','.join(str(x) for x in size_mitigation_parameters), ' - large cube limit exceeded' if (('spw' in size_mitigation_parameters) and large_cube_mitigation) else ''), \
                    'shortmsg': 'Size was mitigated'}, \
                   known_synthesized_beams
        else:
            return size_mitigation_parameters, \
                   original_maxcubesize, original_productsize, \
                   cube_mitigated_productsize, \
                   maxcubesize, total_productsize, \
                   original_imsize, mitigated_imsize, \
                   False, \
                   {'longmsg': 'No size mitigation needed', \
                    'shortmsg': 'No size mitigation'}, \
                   known_synthesized_beams


    def mitigate_imsize(self):
        '''
        Mitigate product size by adjusting ppb and imsize only. This is used in the VLA imaging heuristic, see
        PIPE-676.

        Uses the size_mitigation_parameters dictionary similarly to mitigate_sizes() method.
        '''
        # TODO: note that it always assumes continuum imaging mode
        maximsize = self.inputs.maximsize
        if type(maximsize) is not int:
            try:
                maximsize = int(maximsize)
            except ValueError:
                raise ValueError('Argument maximsize has type %s, but integer is expected' % type(maximsize))
        known_synthesized_beams = self.context.synthesized_beams

        # Initialize mitigation parameter dictionary
        # Possible keys:
        # 'nbins', 'hm_imsize', 'hm_cell', 'field'
        size_mitigation_parameters = {}
        multi_target_size_mitigation = {}
        is_mitigated = False
        original_imsize = []
        mitigated_imsize = []

        # Initialize cube specific variables for compatibility with mitigate_sizes
        original_maxcubesize = -1.0
        original_productsize = 0.0
        cube_mitigated_productsize = -1.0
        mitigated_maxcubesize = -1.0
        total_productsize = 0.0

        # Create makeimlist inputs
        makeimlist_inputs = makeimlist.MakeImListInputs(self.context)
        makeimlist_inputs.intent = 'TARGET'
        makeimlist_inputs.specmode = 'cont'
        makeimlist_inputs.clearlist = True
        # calcsb         Force (re-)calculation of sensitivities and beams (Default None)
        makeimlist_inputs.calcsb = None

        # Create makeimlist task for size calculations
        makeimlist_task = makeimlist.MakeImList(makeimlist_inputs)

        # Get default target setup
        makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
        makeimlist_result = makeimlist_task.prepare()
        known_synthesized_beams = makeimlist_result.synthesized_beams
        imlist = makeimlist_result.targets  # at this stage the expected image size is known

        # Loop over imaging targets
        for im in imlist:
            # Mitigation parameters
            im_specific_mitigation = {}
            # Local makeimlist inputs copy for recomputing image size for current (field, intent, spw) combination
            local_makeimlist_inputs = copy.deepcopy(makeimlist_inputs)
            local_makeimlist_inputs.field = im['field']
            local_makeimlist_inputs.spw = im['spw']
            # Requested image size
            imsize_request = im['imsize']
            if len(imlist) == 1:
                original_imsize = imsize_request
            else:
                original_imsize.append(imsize_request)

            # Get original maximum cube and product sizes for compatibility
            _, _, _, im_productsize = self.calculate_sizes([im])
            original_productsize += im_productsize

            LOG.info('Default imaging leads to image pixel count of %s for target %s' % (imsize_request, im['field']))
            LOG.info('Allowed maximum image pixel count: %s.' % ([maximsize, maximsize]))

            if max(imsize_request) > maximsize:
                # If too large, try changing pixperbeam setting
                im_specific_mitigation['hm_cell'] = '4ppb'
                LOG.info('Size mitigation: Setting hm_cell to %s for target %s' % (im_specific_mitigation['hm_cell'],
                                                                                   im['field']))

                # Recalculate sizes with mitigation
                local_makeimlist_inputs.hm_cell = im_specific_mitigation['hm_cell']
                local_makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                local_makeimlist_task = makeimlist.MakeImList(local_makeimlist_inputs)
                local_makeimlist_result = local_makeimlist_task.prepare()
                known_synthesized_beams = local_makeimlist_result.synthesized_beams
                local_imlist = local_makeimlist_result.targets
                # New sizes
                cubesizes, maxcubesize, productsizes, im_productsize = self.calculate_sizes(local_imlist)

                # Compute current sizes
                imsize_request = local_imlist[0]['imsize']
                LOG.info('hm_cell mitigation leads to image pixel count of %s for target %s' % (imsize_request,
                                                                                                im['field']))

            if max(imsize_request) > maximsize:
                # If still too large, try changing pixperbeam setting
                imsize_request = [maximsize, maximsize]
                im_specific_mitigation['hm_cell'] = '4ppb'
                im_specific_mitigation['hm_imsize'] = imsize_request

                # Recalculate sizes with mitigation
                local_makeimlist_inputs.hm_cell = im_specific_mitigation['hm_cell']
                local_makeimlist_inputs.hm_imsize = im_specific_mitigation['hm_imsize']
                makeimlist_inputs.known_synthesized_beams = known_synthesized_beams
                makeimlist_task = makeimlist.MakeImList(makeimlist_inputs)
                makeimlist_result = makeimlist_task.prepare()
                known_synthesized_beams = makeimlist_result.synthesized_beams
                local_imlist = makeimlist_result.targets
                # New sizes
                cubesizes, maxcubesize, productsizes, im_productsize = self.calculate_sizes(local_imlist)

                LOG.info('Size mitigation: image pixel count is still larger than allowed for target %s. Truncating '
                         'image.' % (im['field']))
                LOG.info('Size mitigation: Setting hm_cell to %s for target %s' % (im_specific_mitigation['hm_cell'],
                                                                                   im['field']))
                LOG.info('Size mitigation: Setting hm_imsize to %s for target %s' % (im_specific_mitigation['hm_imsize'],
                                                                                     im['field']))

            # Save cube mitigated product size for logs
            total_productsize += im_productsize
            if len(imlist) == 1:
                mitigated_imsize = imsize_request
            else:
                mitigated_imsize.append(imsize_request)

            # Store mitigation parameters per spw list
            multi_target_size_mitigation[im['spw']] = im_specific_mitigation
            if im_specific_mitigation != {}:
                is_mitigated = True

        # Store imaging target specific parameters in mitigation dictionary only if imsize is mitigated
        if is_mitigated:
            size_mitigation_parameters['multi_target_size_mitigation'] = multi_target_size_mitigation

        if is_mitigated:
            return size_mitigation_parameters, \
                   original_maxcubesize, original_productsize, \
                   cube_mitigated_productsize, \
                   mitigated_maxcubesize, total_productsize, \
                   original_imsize, mitigated_imsize, \
                   False, \
                   {'longmsg': 'Size had to be mitigated (%s)' % (','.join(str(x) for x in size_mitigation_parameters)), \
                    'shortmsg': 'Size was mitigated'}, \
                   known_synthesized_beams
        else:
            return size_mitigation_parameters, \
                   original_maxcubesize, original_productsize, \
                   cube_mitigated_productsize, \
                   mitigated_maxcubesize, total_productsize, \
                   original_imsize, mitigated_imsize, \
                   False, \
                   {'longmsg': 'No size mitigation needed', \
                    'shortmsg': 'No size mitigation'}, \
                   known_synthesized_beams
