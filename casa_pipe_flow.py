import glob
import pipeline

from pipeline.h.cli import h_init
from pipeline.h.cli import h_tsyscal
from pipeline.h.cli import h_save

from pipeline.hsd.cli import *

from prefect import flow

@flow
def replay():
    pipeline.initcli()

    __rethrow_casa_exceptions = True
    context = h_init()

    asdms = glob.glob('../rawdata/uid___A002_X*')
    asdms.sort()
    session = ['default' for _ in asdms]

    try:
        results = hsd_importdata(vis=asdms, session=session)
        results = hsd_flagdata(results=results)
        results = h_tsyscal(results=results)
        results = hsd_tsysflag(results=results)
        results = hsd_skycal(results=results)
        results = hsd_k2jycal(results=results)
        results = hsd_applycal(results=results)
        results = hsd_atmcor(results=results)
        results = hsd_baseline(results=results)
        results = hsd_blflag(results=results)
        results = hsd_baseline(resultst=results)
        results = hsd_blflag(results=results)
        results = hsd_imaging(results=results)
        results = hsd_exportdata(results=results)
    finally:
        h_save()

if __name__ == "__main__":
    replay()

