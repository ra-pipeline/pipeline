import copy
import os.path

import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.imagelibrary as imagelibrary
import pipeline.infrastructure.utils as utils
from pipeline import infrastructure
from pipeline.hif.tasks.makeimlist.cleantarget import CleanTargetInfo

LOG = infrastructure.logging.get_logger(__name__)


class MakeImagesResult(basetask.Results):
    def __init__(self):
        super().__init__()
        self.targets = []
        self.results = []
        self.plot_path = None
        self.mitigation_error = False
        self.sensitivities_for_aqua = []
        self.logrecords = []
        self.overwrite_on_export = True

    def add_result(self, result, target, outcome):
        target['outcome'] = outcome
        # Remove heuristics object to avoid accumulating large amounts of unnecessary memory
        del target['heuristics']
        self.targets.append(target)
        self.results.append(result)

        # pull the log records from the worker results, potentially executing
        # on MPI servers, into this object
        self.logrecords.extend(getattr(result, 'logrecords', []))

    def set_info(self, info):
        self.clean_list_info = info

    def merge_with_context(self, context):
        """Add the cleaned targets to the context."""

        for result in self.results:
            try:
                img_params = {kk: vv['imaging_params'] for (kk, vv) in result.iterations.items()}
                imageitem = imagelibrary.ImageItem(
                    imagename=result.image, sourcename=result.sourcename,
                    spwlist=result.spw, specmode=result.hm_specmode,
                    sourcetype=result.intent,
                    stokes=result.stokes,
                    datatype=result.datatype,
                    multiterm=result.multiterm,
                    metadata=result.imaging_metadata,
                    imaging_params=img_params,  # imaging parameters for each iteration
                    imageplot=result.imageplot,
                    imagename_prefix=result.inputs['image_heuristics'].imagename_prefix)
                if 'TARGET' in result.intent:
                    context.sciimlist.add_item(imageitem, self.overwrite_on_export)
                else:
                    context.calimlist.add_item(imageitem, self.overwrite_on_export)
            except Exception as ex:
                LOG.debug('Failed to add imageitem to context from %s: %s', result, ex)

        # Save quantities in the context for later stages
        skip_recalc = False
        for result in self.results:
            # Calculated beams for later stages
            if result.synthesized_beams is not None:
                if 'recalc' in result.synthesized_beams:
                    context.synthesized_beams = copy.deepcopy(result.synthesized_beams)
                    del context.synthesized_beams['recalc']
                else:
                    utils.update_beams_dict(context.synthesized_beams, result.synthesized_beams)

            # Calculated sensitivities for later stages
            if result.per_spw_cont_sensitivities_all_chan is not None:
                if 'recalc' in result.per_spw_cont_sensitivities_all_chan and not skip_recalc:
                    context.per_spw_cont_sensitivities_all_chan = copy.deepcopy(result.per_spw_cont_sensitivities_all_chan)
                    del context.per_spw_cont_sensitivities_all_chan['recalc']
                    # Copy only the first recalculated dictionary
                    skip_recalc = True
                else:
                    utils.update_sens_dict(context.per_spw_cont_sensitivities_all_chan, result.per_spw_cont_sensitivities_all_chan)

            # Clean masks and thresholds for later stages
            if result.stokes == 'I' and (result.cleanmask not in (None, '')):
                cleanTargetKey = CleanTargetInfo(datatype=result.datatype, field=result.sourcename,
                                                 intent=result.intent, virtspw=result.spw, stokes=result.stokes, specmode=result.hm_specmode)
                context.clean_masks[cleanTargetKey] = result.cleanmask
                context.clean_thresholds[cleanTargetKey] = result.threshold

        # empty the pending list and message
        context.clean_list_pending = []
        context.clean_list_info = {}

        # Remove heuristics objects to avoid accumulating large amounts of unnecessary memory
        for target in self.inputs['target_list']:
            try:
                del target['heuristics']
            except:
                pass

        for result in self.results:
            try:
                del result.inputs['image_heuristics']
            except:
                pass

    def __repr__(self):
        repr = 'MakeImages:'

        columns = [
            ('field', lambda t: str(t['field'])),
            ('intent', lambda t: str(t['intent'])),
            ('spw', lambda t: str(t['spw'])),
            ('phasecenter', lambda t: str(t['phasecenter'])),
            ('cell', lambda t: str(t['cell'])),
            ('imsize', lambda t: str(t['imsize'])),
            ('imagename', lambda t: os.path.basename(str(t['imagename']))),
            ('outcome', lambda t: str(t['outcome'])),
        ]
        rows = [[getter(target) for _, getter in columns] for target in self.targets]
        widths = [max([len(header)] + [len(row[idx]) for row in rows]) + 1 for idx, (header, _) in enumerate(columns)]

        repr += '\n'
        repr += ''.join(f'{header:{width}}' for (header, _), width in zip(columns, widths))

        for row in rows:
            repr += '\n'
            repr += ''.join(f'{val:{width}}' for val, width in zip(row, widths))

        return repr
