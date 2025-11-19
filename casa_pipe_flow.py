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
        hsd_importdata(vis=asdms, session=session)
        hsd_flagdata()
        h_tsyscal()
        hsd_tsysflag()
        hsd_skycal()
        hsd_k2jycal()
        hsd_applycal()
        hsd_atmcor()
        hsd_baseline()
        hsd_blflag()
        hsd_baseline()
        hsd_blflag()
        hsd_imaging()
        hsd_exportdata()
    finally:
        h_save()

if __name__ == "__main__":
    replay()

