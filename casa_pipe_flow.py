import glob

from prefect import flow

import pipeline
from pipeline.h.cli import h_init, h_save, h_tsyscal
from pipeline.hsd.cli import *


@flow
def load(asdms, session):
    results = hsd_importdata(vis=asdms, session=session)
    results = hsd_flagdata(results=results)
    results = h_tsyscal(results=results)
    results = hsd_tsysflag(results=results)
    results = hsd_skycal(results=results)
    results = hsd_k2jycal(results=results)

    return results


@flow
def process(results):
    results = hsd_applycal(results=results)
    results = hsd_atmcor(results=results)
    results = hsd_baseline(results=results)
    results = hsd_blflag(results=results)
    results = hsd_baseline(resultst=results)
    results = hsd_blflag(results=results)
    results = hsd_imaging(results=results)
    results = hsd_exportdata(results=results)


@flow
def replay():
    pipeline.initcli()

    __rethrow_casa_exceptions = True
    context = h_init()

    asdms = glob.glob("../rawdata/uid___A002_X*")
    asdms.sort()
    session = ["default" for _ in asdms]

    try:
        results = load(asdms=asdms, session=session)
        process(results)

        # results = hsd_importdata(vis=asdms, session=session)
        # results = hsd_flagdata(results=results)
        # results = h_tsyscal(results=results)
        # results = hsd_tsysflag(results=results)
        # results = hsd_skycal(results=results)
        # results = hsd_k2jycal(results=results)
        # results = hsd_applycal(results=results)
        # results = hsd_atmcor(results=results)
        # results = hsd_baseline(results=results)
        # results = hsd_blflag(results=results)
        # results = hsd_baseline(resultst=results)
        # results = hsd_blflag(results=results)
        # results = hsd_imaging(results=results)
        # results = hsd_exportdata(results=results)
    finally:
        h_save()


if __name__ == "__main__":
    replay()
