# `hsd_calimage` Processing Recipe

The following is the ordered list of pipeline processing commands executed by the `hsd_calimage` recipe, as defined in `procedure_hsd_calimage.xml`.

1. {func}`~pipeline.hsd.cli.hsd_importdata` ()
2. {func}`~pipeline.hsd.cli.hsd_flagdata` ()
3. {func}`~pipeline.h.cli.h_tsyscal` ()
4. {func}`~pipeline.hsd.cli.hsd_tsysflag` ()
5. {func}`~pipeline.hsd.cli.hsd_skycal` ()
6. {func}`~pipeline.hsd.cli.hsd_k2jycal` ()
7. {func}`~pipeline.hsd.cli.hsd_applycal` ()
8. {func}`~pipeline.hsd.cli.hsd_atmcor` ()
9. {func}`~pipeline.hsd.cli.hsd_baseline` ()
10. {func}`~pipeline.hsd.cli.hsd_blflag` ()
11. {func}`~pipeline.hsd.cli.hsd_baseline` ()
12. {func}`~pipeline.hsd.cli.hsd_blflag` ()
13. {func}`~pipeline.hsd.cli.hsd_imaging` ()
14. {func}`~pipeline.hsd.cli.hsd_exportdata` ()
