import copy
import os.path

import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.utils as utils


class MakeImListResult(basetask.Results):
    def __init__(self, error=False, error_msg=None):
        super().__init__()
        self.contfile = None
        self.linesfile = None
        self.targets = []
        self.clean_list_info = {}
        self._expected_num_targets = 0
        self.clearlist = True
        self.mitigation_error = False
        self.synthesized_beams = None
        self.error = error
        self.error_msg = error_msg
        self.skip_stage = False

    def add_target(self, target):
        self.targets.append(target)

    def set_info(self, info):
        self.clean_list_info = info

    def merge_with_context(self, context):
        targets_copy = copy.deepcopy(self.targets)

        # replace the foreign observing run in the heuristics with the one in
        # the target context. This helps keep the pickle size down.
        other_obsrun = context.observing_run
        for target in targets_copy:
            h = target['heuristics']
            if hasattr(h, 'observing_run'):
                h.observing_run = other_obsrun

        if self.clearlist:
            context.clean_list_pending = targets_copy
            context.clean_list_info = self.clean_list_info
        else:
            context.clean_list_pending.extend(targets_copy)
            for key, value in self.clean_list_info.items():
                if context.clean_list_info.get(key, None) is not None:
                    context.clean_list_info[key] = '%s %s' % (context.clean_list_info[key], value)
                else:
                    context.clean_list_info[key] = value

        # Remove heuristics objects to avoid accumulating large amounts of unnecessary memory
        for target in self.targets:
            try:
                del target['heuristics']
            except:
                pass

        if self.contfile is not None:
            context.contfile = self.contfile
        if self.linesfile is not None:
            context.linesfile = self.linesfile

        # Calculated beams for later stages
        if self.synthesized_beams is not None:
            if 'recalc' in self.synthesized_beams:
                context.synthesized_beams = copy.deepcopy(self.synthesized_beams)
                del context.synthesized_beams['recalc']
            else:
                utils.update_beams_dict(context.synthesized_beams, self.synthesized_beams)

    @property
    def num_targets(self):
        return len(self.targets)

    @property
    def expected_num_targets(self):
        return self._expected_num_targets

    def set_expected_num_targets(self, expected_num_targets):
        self._expected_num_targets = expected_num_targets

    def __repr__(self):
        repr = 'MakeImList:'

        if len(self.targets) == 0:
            repr += '\n is empty'
            return repr

        columns = [
            ('field', lambda t: str(t['field'])),
            ('intent', lambda t: str(t['intent'])),
            ('spw', lambda t: str(t['spw'])),
            ('phasecenter', lambda t: str(t['phasecenter'])),
            ('cell', lambda t: str(t['cell'])),
            ('imsize', lambda t: str(t['imsize'])),
            ('imagename', lambda t: os.path.basename(str(t['imagename']))),
        ]
        optional_keys = ('specmode', 'start', 'width', 'nbin', 'nchan', 'uvrange')
        columns.extend(
            (key, lambda t, k=key: str(t[k]) if k in t else '')
            for key in optional_keys
            if any(key in target for target in self.targets)
        )

        rows = [[getter(target) for _, getter in columns] for target in self.targets]
        widths = [max([len(header)] + [len(row[idx]) for row in rows]) + 1 for idx, (header, _) in enumerate(columns)]

        repr += '\n'
        repr += ''.join(f'{header:{width}}' for (header, _), width in zip(columns, widths))

        for row in rows:
            repr += '\n'
            repr += ''.join(f'{val:{width}}' for val, width in zip(row, widths))

        return repr
