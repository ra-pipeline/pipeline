

# VLASS Selfcal & Restore

* VLASS selfcal workflow

    ```python
    hif_makeimages (tclean:savemodel)
    hifv_selfcal (gaincal,applycal)
    hif_makeimages (tclean)
    ```

* VLASS selfcal/restore workflow

    ```python
    hifv_restorpims
        MakeImages
        applycal
        statwt
        ...
    ```

# auto_selfcal prototype

```console
per target per band
    tclean(data,dirty)
    tclean(data,initial)
per target per band per spw (optional)
    tclean(data,dirty)
    tclean(data,initial)        

per target per band
    solint1->solint2->solint3->...solintX
        tclean:savemodel(data,priorcal)
        per MS
            gaincal
        per MS
            applycal
        tclean(corrected,resume-model,postcal)
    solintX-1 ("step back" when X is worse than X-1)
        per MS
            appplycal

per target per band
    tclean(corrected,final)
per target per band per spw (optional)
    tclean(corrected,final)

per target 
    per band 
        per MS
            applycal(to originMS): write to a script / or apply on-the-fly
```

# PipelineTask: `hif_selfcal`

```console
MakeImList:cont: derive clean_target_list

per clean_target (i.e. a target/band combination)
    ms_transform()
        * ms per clean_target
        * pointing table hardlinked to the original MS
        
Create copies of temporary context and start using per_clean_target MSs

MakeImList+MakeImages (per clean_target per spw, data, dirty/initial, tier0, optional)

MakeImList:cont+MakeImages (per clean_target, tier0)

    Tclean (per clean_target,tier0) <- selfcal-specific imaging sequence
        CleanBase("iter0","dirty",data)
        CleanBase("iter1","initial",data)

        solint1->solint2->solint3->...solintX ("iter2")
            CleanBase:savemodel(priorcal)
            per MS
                gaincal/applycal
            CleanBase(postcal)
        solintX-1 ("step back" when X is worse than X-1)
            per MS
                appplycal
        
        CleanBase(corrected,"final",'iter3')

MakeImList+MakeImages (per clean_target per spw, corrected, final, tier0, optional)

per clean_target 
    per MS
        applycal(to originMS)

register the datatype per clean_target per MS
```

Note that the model/corrected columns and flagging states of per_clean_target MSes are actively modified during the selfcal operations (notably, the "iter2" step).

## MS/Caltable/Image naming convention (tentative):

### MS names
Assuming that original per-EB input MSes are,

```console
eb1_targets.ms
eb2_targets.ms
eb3_targets.ms
```

the "rebinned MS working copies" generated and used by `hifv_selfcal` will be

```console 
eb1_targets.04287+1801.spw16_18_20_22_24_26_28_30.selfcal.ms
eb2_targets.04287+1801.spw16_18_20_22_24_26_28_30.selfcal.ms
eb3_targets.04287+1801.spw16_18_20_22_24_26_28_30.selfcal.ms
eb1_targets.04288_1802.spw16_18_20_22_24_26_28_30.selfcal.ms
eb2_targets.04288_1802.spw16_18_20_22_24_26_28_30.selfcal.ms
eb3_targets.04288_1802.spw16_18_20_22_24_26_28_30.selfcal.ms
....
```

Note that the original per-EB MSes are split and rebinned into smaller MS quanta, i.e. per-"clean_target" MSes 
"clean_target" here is equivalent to a "target/band" combination in the prototype.
Each of them is a uvdata container that the selfcal "ImageSolver-CalSolver" loop can operate on.
The MS split policy is largely decided due to a CASA limitation that `casatools` doesn't support parallel-write in MS tables (even though `casacore` does via the parallel storage manager `Adios`):
if the uvdata of different "clean_targets" are stored in separate MSes, their selfcal operations, notably the modelcolumn prediction/write, can proceed simultaneously/independently without locking tables; therefore they become tier0-parallelizable.

For the selfcal logic described in the prototype, splitting the per-EB MSes into per_clean_target MSes generally doesn't produce duplications of bulky visibility records (time, uvw, data, etc.).
This is in contrast to the situation of splitting by spws of the same source, where certain columns (e.g. uvw, time) get duplicated for each spw. 
However, a plain mstransform() call will still lead to the duplication of the pointing table from input MS, which can degrade the I/O performance and take unnecessary storage space.
We manage this issue through an I/O-efficient mstransform wrapper function named `ms_transform`: 
by default, the pointing table content of each output MS is hardlinked to the table inside the input MS (see `ms_transform` for details).


### Caltable Names

```console 
eb1_targets.04287+1801.spw16_18_20_22_24_26_28_30.selfcal.ms.hif_selfcal.{stage_label}.{solin}.{caltype}.tbl
...
```

### Image Names

For the selfcal image names, we follow a schema loosely based on the traditional `hif_makeimlist` naming pattern.

Generally, hif_selfcal will produce the following image types:

```
iter0: dirty image generated from data
iter1: "properly-cleaned" image generated from DATA before selfcal (in prototype this is called 'initial')
iter2: 
    iter2_solint1_prior.image: moderately-cleaned image for create selfcal model
    iter2_solint1_post.image: "properly-cleaned" image for selfcal assessment
    iter2_solint2_prior.image: ...
    iter2_solint2_post.image: ...
    ....
iter3: final image generated from corrected data 
```

Here is a practical example of their names:

```
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.I.iter1.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.I.iter2.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.solint1_prior.I.iter2.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.solint1_post.I.iter2.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.solint2_prior.I.iter2.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.solint2_post.I.iter2.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.solint3_prior.I.iter2.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.solint3_post.I.iter2.image
oussid.s2_2.04287+1801_sci.spw16_18_20_22_24_26_28_30.cont.I.iter3.image
```
