====================================
Roadmap & Branching Strategy
====================================

.. contents:: Table of Contents
   :depth: 2
   :local:

--------

PL2026 Timeline
---------------

The following Gantt chart illustrates the complete PL2026 development timeline, including management activities, development phases, ALMA testing cycles, and delivery milestones.

.. mermaid::

    gantt
        title PL2026 Timeline
        dateFormat  YYYY-MM-DD
        tickInterval 1month
        excludes weekends

        section Management
        Stakeholder Planning & Prioritization       :active, des1, 2025-10-01, 2025-12-31
        Team F2F Meeting, Charlottesville, VA       :active,       2025-10-13, 5d
        Inform ALMA AQUA/Archive of New Products    :active, milestone, 2026-05-01, 1d

        section Development
        New Features, Bugfixes, Refactoring, Testing, Documentation :active,       2026-01-01, 2026-07-01
        VLASS Feature Dev Complete            :active, milestone, 2026-02-01, 1d
        VLASS Branch release/2026.1.0         :active, milestone, 2026-02-15, 1d
        CASA Branch PL2026                    :active, milestone, 2026-02-15, 1d
        ALMA/VLA Feature Dev Complete         :active, milestone, 2026-07-01, 1d
        ALMA/VLA Branch release/2026.2.0      :active, milestone, 2026-07-01, 1d
        Optimization & Bugfixes               :active, 2026-07-01, 2026-07-31

        section ALMA Testing
        Ref. Benchmark (late-PL2025)         :active, 2025-10-01, 2025-11-15
        Ref. Benchmark (early-PL2026)        :active, 2026-02-15, 2026-03-31
        Validation Benchmark (PL2026)        :active, 2026-06-15, 2026-07-31
        TRR1                                 :test2, 2026-05-15, 2026-05-29
        TRR2                                 :test3, 2026-07-10, 2026-07-24
        Accept. Rev.                         :test4, 2026-08-14, 2026-09-02
        JAO-ARC Validation Test              :test5, 2026-09-05, 2026-09-14

        section Delivery
        ALMA Cycle-12 and VLA/SRDP Pipeline (2025.1.0.35, CASA 6.6.6-17-py3.10)  :done, crit, milestone, 2025-10-01, 1d
        VLASS Pipeline (2026.1.0, CASA 6.7.1-py3.10+gpu)             :active, crit, milestone, 2026-03-15, 1d
        ALMA E2E13 Pre-release                :active, crit, milestone, 2026-07-10, 1d
        ALMA Cycle-13 and VLA/SRDP Pipeline (2026.2.0, CASA 6.7.x-py3.12)     :active, crit, milestone, 2026-08-01, 1d

--------

Key Milestones
--------------

Delivery Schedule
^^^^^^^^^^^^^^^^^

:October 2025:
    **ALMA Cycle-12 and VLA/SRDP Pipeline**
    
    * Version: 2025.1.0.35
    * CASA: 6.6.6-17-py3.10
    * Status: Completed

:March 2026:
    **VLASS Pipeline**
    
    * Version: 2026.1.0
    * CASA: 6.7.1-py3.10+gpu
    * Status: In Development

:July 2026:
    **ALMA E2E13 Pre-release**
    
    * Version: 2026.2.0 (pre-release)
    * Status: Planned

:August 2026:
    **ALMA Cycle-13 and VLA/SRDP Pipeline**
    
    * Version: 2026.2.0
    * CASA: 6.7.x-py3.12
    * Status: Planned

--------

PL2025/2026 Branching Strategy
------------------------------

The branching diagram below illustrates the development workflow across PL2025 and PL2026 cycles, showing the relationship between the main development branch and release branches.

Branch Overview
^^^^^^^^^^^^^^^

* **Main Branch**: Continuous development with new features and improvements
* **release/2025.1.0**: Stable release for ALMA Cycle-12 (CASA 6.6.6-py3.10)
* **release/2026.1.0**: VLASS-focused release (CASA 6.7.1-py3.10+hpg)
* **release/2026.2.0**: ALMA Cycle-13 and VLA release (CASA 6.7.x-py3.12)

.. mermaid::

    ---
    title: PL2025/2026 Branching
    config:
        logLevel: 'debug'
        theme: 'base'
        gitGraph:
            showBranches: true
            showCommitLabel: true
            mainBranchOrder: 1
    ---

    gitGraph
        %% === Initial 2025 Development on Main ===
        commit id:"feature1"
        commit id:"feature2"
        commit id:"feature3"
        commit id:"bugfix1" tag:"2025.0.2.14" tag:"2025.1.0.0" tag:"2025.1.1.0"

        %% --- Branch for 2025.1.0 Release ---
        branch "release/2025.1.0 (casa-6.6.6-py3.10)" order: 0
        checkout "release/2025.1.0 (casa-6.6.6-py3.10)"
        commit id:"bugfix2"
        commit id:"bugfix3" tag:"2025.1.0.35" type: HIGHLIGHT
        checkout main

        %% === Continued Development on Main ===
        commit id:"refactor1"
        commit id:"refactor2"
        branch "feature4" order: 2
        checkout "feature4"
        commit id:"feature4-pt1"
        commit id:"feature4-pt2"
        checkout main
        cherry-pick id:"bugfix2" tag:"2025.1.1.x"
        cherry-pick id:"bugfix3" tag:"2025.1.1.27"
        merge "feature4" id:"merge:feature4"
        commit id:"feature4"
        commit id:"bugfix4" tag:"2025.1.1.10"
        commit id:"feature5"
        commit id:"feature6" tag:"2026.0.0.0"

        %% === VLASS 2026 Development ===
        commit id:"feature7"
        commit id:"bugfix5" tag:"2026.0.1.0"
        commit id:"bugfix6"
        commit id:"feature8" tag:"2026.0.1.14" tag:"2026.1.0.0" tag:"2026.1.1.0"

        %% --- Branch for 2026.1.0 (VLASS) Release ---
        branch "release/2026.1.0 (casa-6.7.1-py3.10+hpg)" order: 3
        checkout "release/2026.1.0 (casa-6.7.1-py3.10+hpg)"
        commit id:"bugfix7"
        commit id:"bugfix8" tag:"2026.1.0.2"
        commit id:"hotfix1"
        commit id:"hotfix2" tag:"2026.1.0.3" type: HIGHLIGHT
        checkout main

        %% === ALMA/VLA 2026 Development ===
        commit id:"feature9" tag:"2026.1.1.1"
        cherry-pick id:"bugfix7" tag:"2026.1.1.2"
        commit id:"feature10"
        commit id:"feature11" tag:"2026.1.2.0"
        commit id:"feature12"
        commit id:"bugfix9" tag:"2026.1.3.7" tag:"2026.2.0.0" tag:"2026.3.0.0"

        %% --- Branch for 2026.2.0 (ALMA/VLA) Release ---
        branch "release/2026.2.0 (casa-6.7.x-py3.12)" order: 4
        checkout "release/2026.2.0 (casa-6.7.x-py3.12)"
        commit id:"bugfix10"
        commit id:"hotfix3" tag:"2026.2.0.5"
        checkout main

        %% === Post-Release Maintenance & Mainline Dev ===
        commit id:"refactor3" tag:"2026.3.0.1"
        commit id:"bugfix11" tag:"2026.2.0.2"
        cherry-pick id:"hotfix3" tag:"2026.3.0.7"
        commit id:"refactor4"
        commit id:"refactor5"
        checkout "release/2026.2.0 (casa-6.7.x-py3.12)"
        cherry-pick id:"bugfix11" tag:"2026.2.0.3"
        commit id:"hotfix4" tag:"2026.2.0.4" type: HIGHLIGHT

--------

Branching Workflow
------------------

Development Phases
^^^^^^^^^^^^^^^^^^

1. **Feature Development**
   
   * New features developed on main branch
   * Feature branches merged back to main
   * Regular integration and testing

2. **Release Branching**
   
   * Release branches created at feature freeze
   * Stabilization and bug fixes on release branches
   * Critical fixes cherry-picked back to main

3. **Maintenance**
   
   * Hotfixes applied to release branches
   * Important fixes backported as needed
   * Main branch continues with new development

Version Numbering
^^^^^^^^^^^^^^^^^

The project follows `semantic versioning <https://peps.python.org/pep-0440/#semantic-versioning>`_ with the format: ``YEAR.MAJOR.MINOR.MICRO``

* **YEAR**: Calendar year (e.g., 2025, 2026)
* **MAJOR**: Major release number within the year
* **MINOR**: Minor feature releases
* **MICRO**: Merges of features, bug fixes and hotfixes

--------

.. note::
   For detailed information about specific releases or development schedules, please refer to the project documentation or contact the development team.