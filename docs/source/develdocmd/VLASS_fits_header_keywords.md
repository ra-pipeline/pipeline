# VLASS FITS Header Keywords

This document describes the header keywords added to VLASS FITS files as part of **PIPE-2461** and **PIPE-3040**. These keywords provide additional metadata describing the data processing and improve the overall data characterization.

To distinguish the newly introduced keywords from existing FITS header keywords, all new keywords are prefixed with `VLASS`. Below is a list of the keywords, along with their possible values and associated comments.

- **VLASSITY**: Specifies the VLASS image type. Allowed values are `INTENSITY_PBCOR_TT0 | INTENSITY_PBCOR_TT1 | RMS_TT0 | RMS_TT1 | ALPHA | ALPHAERR`.

- **VLASSPT**: Specifies the VLASS product type, identifying the imaging mode of the data product (Quick Look, SE imaging, or cube imaging), with possible values `QL | SE | CC`.

- **VLASSTN**: Identifies the VLASS tile name corresponding to the observed sky region. The value is decoded from the file name. If no tile name is found, it is set to an empty string (`''`).

- **VLASSEP**: Specifies the VLASS epoch. The value is decoded from the file name. If no epoch is found, it is set to an empty string (`''`).

- **VLASSVR**: Specifies the VLASS version number. The value is decoded from the file name. If no version is found, it is set to an empty string (`''`).

- **VLASSPC**: Specifies the VLASS phase center corresponding to the pointing center of the observation.

- **VLASSPL**: Specifies the VLASS Stokes/polarization parameter. Allowed values are `I | Q | U | V | L | IQU | IQUV`.

- **VLASSRJ**: Indicates whether the plane is rejected for VLASS CC processing; value is a boolean (`T | F`).

- **VLASSSPW**: Specifies the spectral window ID(s) used for image generation; value is `<spw-id>`.

- **VLASSRMS**: Specifies the median RMS values computed from the Stokes I RMS images (`RMS_TT0` and `RMS_TT1`). The `RMS_TT0` value is used for `*TT0`, `*RMS_TT0`, `ALPHA`, and `ALPHA_ERROR` images, while the `RMS_TT1` value is used for `*TT1` and `*RMS_TT1` images.

- **VLASSPK**: Specifies the peak flux density computed from the Stokes I primary beam corrected images (`INTENSITY_PBCOR_TT0` and `INTENSITY_PBCOR_TT1`). The TT0 peak value is used for `*TT0`, `*RMS_TT0`, `ALPHA`, and `ALPHA_ERROR` images, while the TT1 peak value is used for `*TT1` and `*RMS_TT1` images.

- **VLASSBWN**: Specifies the nominal bandwidth of the VLASS observation. For SE and QL products, the bandwidth is 2 GHz, while for CC products it is 128 MHz.

- **VLASSBW**: Specifies the effective bandwidth after flagging. It is computed as the number of non-flagged channels multiplied by the channel width.

---

## Processing Notes

The `hif_makeimages` task adds the `VLASSITY`, `VLASSPT`, `VLASSTN`, `VLASSEP`, `VLASSVR`, `VLASSPC`, `VLASSPL`, `VLASSRJ`, `VLASSSPW`, `VLASSBWN`, and `VLASSBW` keywords to the CASA image header. However, the `VLASSPK` and `VLASSRMS` keywords are added in the `hif_makecutoutimages` task.

All keywords are carried over to the FITS header during the conversion process in the `hifv_exportvlassdata` task. In the case of cube imaging, the images are split by Stokes parameter, and for these products the `VLASSPL`, `VLASSPK`, and `VLASSRMS` keywords are updated during `hifv_exportvlassdata`.

Additionally, the comments associated with these keywords are added in the `hifv_exportvlassdata` task after creation of the FITS file, since CASA image headers do not support keyword comments.