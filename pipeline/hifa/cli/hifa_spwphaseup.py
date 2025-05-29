import pipeline.h.cli.utils as utils

from .hifa_spwmapping import hifa_spwmapping


@utils.deprecated("Use 'hifa_spwmapping' instead.")
def hifa_spwphaseup(*args, **kwargs):
    "DEPRECATED: `hifa_spwphaseup` has been renamed to `hifa_spwmapping` (see PIPE-2620). Use `hifa_spwmapping` instead."
    return hifa_spwmapping(*args, **kwargs)
