Pipeline
========
*The operational data processing pipelines for ALMA, VLA, and the NRO 45m telescope.*

|Docs Pages| |Docs RTD| |Test Unit| |Codecov Unit|

.. important::
    This site provides *up-to-date and version-controlled* information, *automatically generated from the code repository*, to complement the official Pipeline portals from `ALMA <https://almascience.nrao.edu/processing/science-pipeline>`_ and `VLA <https://science.nrao.edu/facilities/vla/data-processing>`_.
    
    Pipeline documentation is in transition, and not all content is migrated here - the table below clarifies where to find different content. Some content is intended for Users, and some for Developers, but naturally there is significant overlap.
       
    Pipeline development is a collaborative effort led by `NRAO`_, `ESO`_, and `NAOJ`_, with additional contributions from `MPIfR`_, `NOVA`_ (from 2026), and `UKATC`_ (until 2025) under contract to `ESO`_.

.. important::
   Please :doc:`Acknowledge <acknowledgement>` the Pipeline in your publications.
    

Official Repository
-------------------

The official public code repository is accessible here:  - `Open Bitbucket @ NRAO - PIPE <https://open-bitbucket.nrao.edu/projects/PIPE>`_

Documentation Components
------------------------

.. list-table::
   :header-rows: 1
   :widths: 40 40
   :class: pipedocs-frontpage

   * - Content
     - Location
   * - ALMA User's Guide :sup:`1`
     - `PDF <users_guide.pdf>`__ :doc:`HTML <users_guide/index>`
   * - ALMA Pipeline Known Issues :sup:`2`
     - :doc:`ALMA Known Issues <users_guide/known_issues>`
   * - VLA User's Guide
     - `VLA Processing <https://science.nrao.edu/facilities/vla/data-processing>`__ (NRAO site)
   * - VLA Data processing Known Issues
     - `VLA Known Issues <https://science.nrao.edu/facilities/vla/data-processing/pipeline#autotoc-item-autotoc-32>`__ (NRAO site)
   * - Nobeyama User's Guide
     - `Nobeyama User's Guide <https://www.nro.nao.ac.jp/projects/45m/data/otf/#casa>`__ (NRO site)
   * - How to run the pipeline as a user
     - :doc:`Quick Start <users_guide/quick-start>`
   * - Past releases, all observatories
     - :doc:`Releases <releases>`
   * - Past releases used for ALMA processing
     - `ALMA Processing <https://almascience.nrao.edu/processing/science-pipeline>`__ (ALMA site)
   * - Documentation and API for each task :sup:`3`
     - `PDF <taskdocs.pdf>`__ :doc:`HTML <apisummary>`

.. only:: internal

   Developer & Internal Documentation
   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  

   .. list-table::
      :widths: 40 40
      :class: pipedocs-frontpage

      * - How to run the pipeline as a developer
        - :doc:`Running Pipeline <devel/usage/running_pipeline>`
      * - Pixi Workflow for Development
        - :doc:`Pixi Tasks <devel/setup/pixi_tasks>`
      * - Building & Publishing Documentation
        - :doc:`Documentation Builds <devel/setup/readthedocs>`
      * - Pipeline Dependencies
        - :doc:`Dependencies <dependencies>`




:sup:`1` previous versions were in pdf form at `ALMA Processing <https://almascience.nrao.edu/processing/science-pipeline>`__
     
:sup:`2` previously hosted on `casaguides <https://casaguides.nrao.edu/index.php/ALMA_Pipeline_Known_Issues>`__

:sup:`3` previously the Reference Manual in pdf form at `ALMA Processing <https://almascience.nrao.edu/processing/science-pipeline>`__



.. _NRAO: http://www.nrao.edu  
.. _ESO: https://www.eso.org  
.. _UKATC: https://www.ukatc.stfc.ac.uk  
.. _MPIfR: https://www.mpifr-bonn.mpg.de  
.. _NOVA: https://nova-astronomy.nl/  
.. _NAOJ: https://www.nao.ac.jp  

.. |Docs Pages| image:: https://img.shields.io/github/actions/workflow/status/ra-pipeline/pipeline/build-gh-pages-pixi.yml?style=plastic&logo=githubactions&label=docs-pages
  :target: https://github.com/ra-pipeline/pipeline/actions/workflows/build-gh-pages-pixi.yml
  :alt: Docs: GH-Pages-Status

.. |Docs RTD| image:: https://img.shields.io/readthedocs/pipe-docs?style=plastic&logo=readthedocs&label=docs-rtd
  :target: https://pipe-docs.readthedocs.io/en/latest/?badge=latest
  :alt: Docs: RTD-Status

.. |Test Unit| image:: https://img.shields.io/github/actions/workflow/status/ra-pipeline/pipeline/test-unit-pixi.yml?style=plastic&logo=githubactions&label=test-unit
  :target: https://github.com/ra-pipeline/pipeline/actions/workflows/test-unit-pixi.yml
  :alt: Test: GH-Test-Unit-Status

.. |Codecov Unit| image:: https://img.shields.io/codecov/c/github/ra-pipeline/pipeline?style=plastic&label=codecov-unit
  :target: https://app.codecov.io/github/ra-pipeline/pipeline
  :alt: Test: Codecov-Unit-Status

