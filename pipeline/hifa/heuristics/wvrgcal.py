import numpy as np

import pipeline.infrastructure as infrastructure
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.utils import deduplicate, list_to_str

LOG = infrastructure.get_logger(__name__)


class WvrgcalHeuristics:
    def __init__(self, context, vis, hm_tie, tie, hm_smooth, smooth, sourceflag, nsol, segsource):
        self.context = context
        self.vis = vis
        self.hm_smooth = hm_smooth
        self._smooth = smooth
        self._wvr_available = True

        ms = context.observing_run.get_ms(name=vis)

        if hm_smooth == 'manual':
            self._smooth = smooth
        else:
            self._smooth = self._calculate_smooth(ms)

        if hm_tie == 'manual':
            self._tie = tie
        else:
            self._tie = self._calculate_tie(ms)

        # sort out segsource whose valid value is dependent on tie
        if self._tie != []:
            self._segsource = True
        else:
            if segsource is None:
                self._segsource = True
            else:
                self._segsource = segsource

        # sort out sourceflag whose valid value is dependent on segsource
        if sourceflag is None:
            self._sourceflag = []
        else:
            self._sourceflag = sourceflag
        if self._sourceflag != [] and not self._segsource:
            raise Exception('WvrgHeuristics:sourceflag incompatible with segsource False')  

        if nsol is None:
            self._nsol = 1
        else:
            self._nsol = nsol
        if self._nsol != 1 and self._segsource:
            raise Exception('WvrgHeuristics: nsol <>1 incompatible with segsource True')  

    def _calculate_smooth(self, ms):
        # get info on all spectral windows
        self.spws = ms.spectral_windows
        for spw in self.spws:
            LOG.debug('SpW id:%s nchan:%s intents:%s' % (spw.id,
              spw.num_channels, spw.intents))

        # Get the data_desc_ids of the wvr data.
        wvr_spw = [spw for spw in self.spws if spw.num_channels == 4 and 'WVR' in spw.intents]

        # Check that wvr data are available
        if wvr_spw == []:
            # EARLY RETURN HERE
            self._wvr_available = False
            return

        wvr_dd_ids = [ms.get_data_description(spw).id for spw in wvr_spw]
        LOG.info('WVR data_desc_id is %s' % wvr_dd_ids)

        # now get the science spws, those used for scientific intent
        science_spws = [spw for spw in self.spws
                        if spw.num_channels not in [1, 4] and
                        not spw.intents.isdisjoint(['BANDPASS', 'AMPLITUDE', 'PHASE', 'TARGET'])]
        LOG.info('science spws are: %s' % [spw.id for spw in science_spws])

        # and the science fields/states
        science_field_ids = [field.id for field in ms.fields
                             if not set(field.intents).isdisjoint(['BANDPASS', 'AMPLITUDE', 'PHASE', 'TARGET'])]
        science_state_ids = [state.id for state in ms.states
                             if not set(state.intents).isdisjoint(['BANDPASS', 'AMPLITUDE', 'PHASE', 'TARGET'])]

        # get the median integration time for wvr data associated with
        # science targets, warn if there is a range of values
        with casa_tools.TableReader(ms.name) as table:
            taql = '''(STATE_ID IN %s AND FIELD_ID IN %s AND
              DATA_DESC_ID in %s)''' % (list_to_str(science_state_ids), list_to_str(science_field_ids), list_to_str(wvr_dd_ids))
            subtable = table.query(taql)
            integration = subtable.getcol('INTERVAL')
            self.wvr_integration = np.median(integration)
            wvr_max_integration = np.max(integration)
            wvr_min_integration = np.min(integration)
            subtable.done()

        LOG.info('median WVR integration time: %s' % self.wvr_integration)
        if wvr_max_integration != self.wvr_integration:
            LOG.warning('max WVR integration time is different: %s' % wvr_max_integration)
        if wvr_min_integration != self.wvr_integration:
            LOG.warning('min WVR integration time is different: %s' % wvr_min_integration)

        # get the median integration time for science data associated with
        # science targets, warn if there is a range of values
        self.science_integration = {}
        science_max_integration = {}
        science_min_integration = {}
        with casa_tools.TableReader(ms.name) as table:
            for spw in science_spws:
                dd_id = ms.get_data_description(spw).id
                taql = '''(STATE_ID IN %s AND FIELD_ID IN %s AND
                  DATA_DESC_ID in %s)''' % (list_to_str(science_state_ids), list_to_str(science_field_ids), dd_id)
                subtable = table.query(taql)
                integration = subtable.getcol('INTERVAL')

                self.science_integration[spw.id] = np.median(integration)
                science_max_integration[spw.id] = np.max(integration)
                science_min_integration[spw.id] = np.min(integration)
                LOG.info('SpW %s median science integration time: %s' % (spw.id, self.science_integration[spw.id]))

                if self.science_integration[spw.id] != science_max_integration[spw.id]:
                    LOG.warning('max science integration time is different: %s' % science_max_integration[spw.id])
                if self.science_integration[spw.id] != science_min_integration[spw.id]:
                    LOG.warning('min science integration time is different: %s' % science_max_integration[spw.id])

                # free the resources held by the sub-table
                subtable.done()

    def _calculate_tie(self, ms):
        # get target ids and directions
        targets = [(field.id, field.name, field.mdirection) for field in ms.fields if 'TARGET' in field.intents]
        if not targets:
            LOG.debug('No science targets in %s', ms.basename)
            return []

        # tie all target fields, assuming they are close to each other
        tied_targets_ids = [target[0] for target in targets]
        tied_targets_names = [target[1] for target in targets]

        # get ids and directions of phase calibrators
        #     this may be a cycle 0 relic and need modification in the future so
        #     that multiple intents are properly handled
        phases = [(field.id, field.name, field.mdirection) for field in ms.fields
                  if 'PHASE' in field.intents
                  and 'BANDPASS' not in field.intents
                  and 'AMPLITUDE' not in field.intents]

        # add phase calibrators to tie if they are less than 15 degrees from target
        tied_phases_ids = []
        tied_phases_names = []
        for phase in phases:
            separation = casa_tools.measures.separation(phase[2], targets[0][2])
            LOG.info('Calibrator: %s (id: %s) distance from target: %s%s',
                     phase[1], phase[0], separation['value'], separation['unit'])
            if casa_tools.quanta.le(separation, '15deg'):
                tied_phases_ids.append(phase[0])
                tied_phases_names.append(phase[1])
        LOG.info('phase calibrators tied to target (ids): %s', tied_phases_ids)
        LOG.info('phase calibrators tied to target (names): %s', tied_phases_names)

        # assemble the full tie
        tied_ids = deduplicate(tied_phases_ids + tied_targets_ids)
        tied_names = deduplicate(tied_phases_names + tied_targets_names)

        LOG.info('Final tied fields (ids): %s', tied_ids)
        LOG.info('Final tied fields (names): %s', tied_names)

        # and format it
        if len(tied_ids) > 1:
            # PIPE-3202/CAS-14850: Due to the field selection parsing behavior of the wvrgcal task's tie parameter,
            # field specifications must be provided as string-formatted IDs rather than field names.
            tie = [str(field_id) for field_id in tied_ids]
            tie = [','.join(tie)]
            return tie
        else:
            return []

    def nsol(self):
        return self._nsol

    def segsource(self):
        return self._segsource

    def smoothall(self, allspws):
        if self.hm_smooth == 'automatic':
            temp = 0.0
            for spw in allspws:
                temp = max(temp, self.science_integration[spw], self.wvr_integration)
            return '%ss' % temp        
        else:
            return self._smooth

    def smooth(self, spw):
        if self.hm_smooth == 'automatic':
            # the wvr integration time is the minimum sensible value for smooth
            temp = max(self.science_integration[spw], self.wvr_integration)
            return '%ss' % temp        
        else:
            return self._smooth

    def sourceflag(self):
        return self._sourceflag

    def tie(self):
        return self._tie

    def toffset(self):
        ms = self.context.observing_run.get_ms(name=self.vis)
        start_time = casa_tools.quanta.quantity(ms.start_time['m0']['value'], ms.start_time['m0']['unit'])

        cut = casa_tools.quanta.quantity(56313, 'd')
        if casa_tools.quanta.gt(start_time, cut):
            LOG.info('MS taken after %s: toffset = 0' % casa_tools.quanta.time(cut, form=['fits']))
            return 0
        else:
            LOG.info('MS taken before %s: toffset = -1' % casa_tools.quanta.time(cut, form=['fits']))
            return -1

    def wvr_available(self):
        return self._wvr_available
