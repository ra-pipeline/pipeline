Pipeline
========
*The operational data processing pipelines for ALMA, VLA, and the NRO 45m telescope.*

|Docs Pages| |Docs RTD| |Test Unit| |Codecov Unit|

.. important::
    This site provides *up-to-date and version-controlled* information, *automatically generated from the code repository*, to complement the official Pipeline portals from `ALMA <https://almascience.nrao.edu/processing/science-pipeline>`_ and `VLA <https://science.nrao.edu/facilities/vla/data-processing>`_.
    
    Pipeline documentation is in transition, and not all content is migrated here - the table below clarifies where to find different content. Some content is intended for Users, and some for Developers, but naturally there is significant overlap.
       
    Pipeline development is a collaborative effort led by `NRAO`_, `ESO`_, and `NAOJ`_, with additional contributions from `MPIfR`_, `NOVA`_ (from 2026), and `UKATC`_ (until 2025) under contract to `ESO`_.



Official Repository
-------------------

The official public code repository is accessible here:  
- `Open Bitbucket @ NRAO - PIPE <https://open-bitbucket.nrao.edu/projects/PIPE>`_

Documentation Components
-----------------------

============================================  ======================
Content                                       Location
============================================  ======================
Past releases, all observatories              :doc:`Releases <releases>` (here)
Past releases used for ALMA data processing   `ALMA Processing <https://almascience.nrao.edu/processing/science-pipeline>`_ (ALMA portal)
--------------------------------------------  ----------------------
ALMA User's Guide                             `ALMA Processing  <https://almascience.nrao.edu/processing/science-pipeline>`_ (ALMA portal)
VLA User's Guide                              `VLA Processing <https://science.nrao.edu/facilities/vla/data-processing>`_ (NRAO site)
How to run the pipeline as a user             in the User's guides
Imaging weights (previously in User's Guide)  :doc:`Imaging Weights <users_guide/weights>` (here)
--------------------------------------------  ----------------------  
Documentation and API for each task           `PDF <https://pipe-docs.readthedocs.io/_/downloads/en/latest/pdf/>`_ :doc:`HTML <apisummary>` (here)
Reference Manual                              replaced by previous line; old versions on `ALMA Processing <https://almascience.nrao.edu/processing/science-pipeline>`_ page
--------------------------------------------  ----------------------
How to run the pipeline as a developer        :doc:`Running Pipeline <devel/usage/running_pipeline>` (here)
Pipeline Dependencies                         :doc:`Dependencies <dependencies>` (here)
============================================  ======================


.. _NRAO: http://www.nrao.edu  
.. _ESO: https://www.eso.org  
.. _UKATC: https://www.ukatc.stfc.ac.uk  
.. _MPIfR: https://www.mpifr-bonn.mpg.de  
.. _NOVA: https://nova-astronomy.nl/  
.. _NAOJ: https://www.nao.ac.jp  

.. |Docs Pages| image:: https://img.shields.io/github/actions/workflow/status/ra-pipeline/pipeline/build-gh-pages.yml?style=plastic&logo=githubactions&label=docs-pages
  :target: https://github.com/ra-pipeline/pipeline/actions/workflows/build-gh-pages.yml
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

