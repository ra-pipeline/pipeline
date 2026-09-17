(sec-acknowledgement)=
# Citations and Acknowledgements

If you use **ALMA data** in your publications, you must include the official acknowledgement text found on the [ALMA publication acknowledgement page](https://almascience.eso.org/alma-data/publication-acknowledgement).

We thank you for additionally acknowledging the use of Pipeline and CASA, using a format similar to the following:

```{parsed-literal}
Data were calibrated using the ALMA Pipeline version 2026.2.0.27 and CASA 6.7.4-8 (:{cite}`2023PASP..135g4501H`, :{cite}`2022PASP..134k4501C`). Calibrated visibilities were downloaded from the ALMA Science Archive and restored, after which the CASA tclean task was used to image those visibilities.
```

:::{important}
Pipeline and CASA are **distinct software packages**, albeit often packaged together — citing both version numbers is essential for reproducibility and credit. See {ref}`Overview <sec-overview>` for more details about the software design.
:::

## Guidelines

* **Pipeline and CASA versions:** Available in the Weblog for all processed data, as well as from the following sources, depending on your delivery method:

  * The ALMA Science Archive (ASA; mirrors at [Europe / ESO](https://almascience.eso.org/aq), [North America / NRAO](https://almascience.nrao.edu/aq), and [East Asia / NAOJ](https://almascience.nao.ac.jp/aq)): included in the README and QA2 report.
  * The [NRAO archive](https://data.nrao.edu): displayed in the Workflow Task dialog under "CASA/Pipeline Version" when launching a processing task.
  * VLA PI data delivery: included in the delivery notification email.
  * North American ALMA LAVA (Labor-saving Added Value Automation) calibrated data service: included in the QA2 report.

* **Software publications:** Depending on the telescope and processing pipeline used, cite the applicable papers:

  * {cite}`2023PASP..135g4501H`: cite when using the ALMA Interferometric Pipeline.
  * {cite}`2020ASPC..527..639M`: cite when using the ALMA Interferometric or Single-Dish Pipeline.
  * {cite}`2020ASPC..527..571K`: cite when using the [VLA](https://science.nrao.edu/facilities/vla/data-processing/pipeline) or [VLASS](https://public.nrao.edu/vlass) Pipeline.
  * {cite}`2022ASPC..532..397N`: cite when using the [Nobeyama 45m (NRO)](https://www.nao.ac.jp/en/telescopes/nobeyama45m) Pipeline.
  * {cite}`2022PASP..134k4501C`: cite for all data processed with CASA.

* **Tailor the statement to your workflow:** Clearly state your specific data processing path — for example, whether you ran the pipeline yourself, calibrated or imaged manually in CASA, or directly used products from the ALMA Science Archive.

* **Acknowledge specialized data services:** Depending on how your data was delivered, please include the corresponding service acknowledgement:

  * EA ARC calibrated data service: Please include:

    ```{code-block} text
    This work makes use of calibrated data products generated with services provided by the East Asian ALMA Regional Center (EA ARC) operated by NAOJ together with ASIAA and KASI.
    ```

  * European ARC CalMS service: See the [European ARC CalMS guidance](https://almascience.org/tools/eu-arc-network/the-european-arc-calms-service).
  * NRAO [AUDI](https://science.nrao.edu/srdp/science-ready-data-products-srdp-for-alma) service: Please include the following acknowledgement and cite {cite}`2020ASPC..527..519L`:
  
    ```{code-block} text
    This work makes use of advanced data products generated with services operated by the National Radio Astronomy Observatory.
    ```
