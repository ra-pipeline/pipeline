# `hsd_calimage` Processing Recipe

The following is the ordered list of pipeline processing commands executed by the `hsd_calimage` recipe, as defined in `procedure_hsd_calimage.xml`.

1. {func}`hsd_importdata <pipeline.hsd.cli.hsd_importdata>` ()
2. {func}`hsd_flagdata <pipeline.hsd.cli.hsd_flagdata>` ()
3. {func}`h_tsyscal <pipeline.h.cli.h_tsyscal>` ()
4. {func}`hsd_tsysflag <pipeline.hsd.cli.hsd_tsysflag>` ()
5. {func}`hsd_skycal <pipeline.hsd.cli.hsd_skycal>` ()
6. {func}`hsd_k2jycal <pipeline.hsd.cli.hsd_k2jycal>` ()
7. {func}`hsd_applycal <pipeline.hsd.cli.hsd_applycal>` ()
8. {func}`hsd_atmcor <pipeline.hsd.cli.hsd_atmcor>` ()
9. {func}`hsd_baseline <pipeline.hsd.cli.hsd_baseline>` ()
10. {func}`hsd_blflag <pipeline.hsd.cli.hsd_blflag>` ()
11. {func}`hsd_baseline <pipeline.hsd.cli.hsd_baseline>` ()
12. {func}`hsd_blflag <pipeline.hsd.cli.hsd_blflag>` ()
13. {func}`hsd_imaging <pipeline.hsd.cli.hsd_imaging>` ()
14. {func}`hsd_exportdata <pipeline.hsd.cli.hsd_exportdata>` ()
