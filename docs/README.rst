Pipeline
========
*The operational data processing pipelines for ALMA, VLA, and the NRO 45m telescope.*

|Docs Pages| |Docs RTD| |Test Unit| |Codecov Unit|

.. important::

   This site provides *up-to-date, automatically generated, and version-controlled* information to complement the official Pipeline portals from `ALMA <https://almascience.nrao.edu/processing/science-pipeline>`_ and `VLA <https://science.nrao.edu/facilities/vla/data-processing>`_.

   Pipeline documentation is in transition, and not all content is migrated here yet - the table below clarifies where to find different content. Some content is intended for Users, and some for Developers, but naturally there is significant overlap.
   
  Pipeline development is a collaborative effort led by `NRAO`_, `ESO`_, and `NAOJ`_, with additional contributions from `MPIfR`_, `NOVA`_ (from 2026), and `UKATC`_ (until 2025) under contract to `ESO`_.



Official Repository
-------------------

The official public code repository is accessible here:  
- `Open Bitbucket @ NRAO - PIPE <https://open-bitbucket.nrao.edu/projects/PIPE>`_

Documentation Components
-----------------------

===========================================  ======================
Content                                      Location
===========================================  ======================
Past releases, all observatories             :doc:`<releases>`
Past releases used for ALMA data processing  `ALMA Portal <https://almascience.nrao.edu/processing/science-pipeline>`
User's Guide General Introduction            `ALMA Portal <https://almascience.nrao.edu/processing/science-pipeline>`
Documentation and API for each task          `PDF <https://pipe-docs.readthedocs.io/_/downloads/en/latest/pdf/>`_ :doc:`HTML <apisummary>`
Reference Manual                             replaced with previous
How to run the Pipeline                      :doc:`<develdocmd/usage/running_pipeline>`
Pipeline Dependencies                        :doc:`<dependencies>`
==========================================   ======================


.. _NRAO: http://www.nrao.edu  
.. _ESO: https://www.eso.org  
.. _UKATC: https://www.ukatc.stfc.ac.uk  
.. _MPIfR: https://www.mpifr-bonn.mpg.de  
.. _NOVA: https://nova-astronomy.nl/  
.. _NAOJ: https://www.nao.ac.jp  

.. |Docs Pages| image:: https://img.shields.io/github/actions/workflow/status/r-xue/pipeline/build-gh-pages.yml?style=plastic&logo=githubactions&label=docs-pages
  :target: https://github.com/r-xue/pipeline/actions/workflows/build-gh-pages.yml
  :alt: Docs: GH-Pages-Status

.. |Docs RTD| image:: https://img.shields.io/readthedocs/pipe-docs?style=plastic&logo=readthedocs&label=docs-rtd
  :target: https://pipe-docs.readthedocs.io/en/latest/?badge=latest
  :alt: Docs: RTD-Status

.. |Test Unit| image:: https://img.shields.io/github/actions/workflow/status/r-xue/pipeline/test-unit.yml?style=plastic&logo=githubactions&label=test-unit
  :target: https://github.com/r-xue/pipeline/actions/workflows/test-unit.yml
  :alt: Test: GH-Test-Unit-Status

.. |Codecov Unit| image:: https://img.shields.io/codecov/c/github/r-xue/pipeline?style=plastic&label=codecov-unit
  :target: https://app.codecov.io/github/r-xue/pipeline
  :alt: Test: Codecov-Unit-Status

