from . import utils


# docstring and type hints: inherits from h.tasks.mstransform.mstransform.MstransformInputs.__init__
@utils.cli_wrapper
def h_mstransform(vis=None, outputvis=None, field=None, intent=None, spw=None, datacolumn=None, chanbin=None,
                  timebin=None, outframe=None, regridms=None, mode=None, start=None, width=None, nchan=None,
                  per_spw=None, per_field=None, parallel=None):
    """Create new MeasurementSets using CASA mstransform task.

    Create new MeasurementSets using the CASA mstransform task.

    """
