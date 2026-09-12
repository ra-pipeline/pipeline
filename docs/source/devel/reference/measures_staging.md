# Node-Local Measures Staging (PIPE-2882)

(sec-measures-staging)=

## Overview and Motivation

CASA relies on external runtime data tables—specifically **geodetic** (IERS Earth orientation and predictive tables) and **ephemerides** (solar system body trajectories)—to calculate astronomical coordinates, observatory frames, and reference frames. In cluster environments and observatory operations, these tables are commonly served from a central network-attached storage (NFS/Lustre) directory, such as `/home/casa/data/distro`.

Automated nightly maintenance jobs (e.g., cron-based `git pull` or `rsync` from upstream IERS/ASTRO feeds) update these tables in-place. However, updating multi-file directory tables across NFS while long-running pipeline jobs are active creates severe operational hazards:

1. **Transient I/O Failures**: Unlinking and replacing composite table files (`table.dat`, `table.f0`, `table.lock`) during active reads produces transient `ENOENT` ("No such file or directory") or `ESTALE` ("Stale file handle") exceptions in C++ `RegularFileIO`, abruptly aborting jobs.
2. **Loss of Scientific Reproducibility**: Modifying predictive leap second or IERS baseline tables mid-run means different stages of the *same* execution operate on different astrometric references.
3. **NFS Lock & Metadata Contention**: Scores of concurrent cluster cores polling identical tables over NFS introduce file lock contention (`table.lock`) and metadata server bottlenecks.

To eliminate these failure modes, the pipeline provides an **automated node-local scratch staging mechanism** ({jira}`PIPE-2882`).

---

## Architecture and Design

When node-local measures staging is enabled, the pipeline automatically snapshots the dynamic measures data into node-local scratch storage before task processing begins.

```
Shared Data Repository (NFS / Lustre / CVMFS)
├── geodetic/ (~9.5 MB)       ──[ Copied in < 0.05s ]──>  Node-Local Scratch ($SLURM_TMPDIR / /tmp)
├── ephemerides/ (~415 MB)    ──[ Symlinked ]──────────>  casarundata_${USER}_${JOBID}_${PID}/
└── static data (~2.9 GB)     ──[ Untouched ]──────────>  Accessed directly via datapath
```

### 1. Hybrid Staging Architecture (~9.5 MB Copy Payload)

While a full CASA runtime data distribution is ~3.3 GB (encompassing beam models, antenna layouts, and catalogs), analysis of upstream update mechanisms reveals:

* **Dynamic tables (`geodetic/`, ~9.5 MB)**: `IERSeop2000`, `IERSpredict`, and `TAI_UTC` are actively updated daily/weekly by the upstream measures cron job (`casaadm` at 02:30 EDT). In-place modification of these active tables over NFS was the root cause of transient `ENOENT` / `ESTALE` crashes ({jira}`PIPE-2882`).
* **Static ephemeris tables (`ephemerides/`, ~415 MB)**: Solar system ephemerides (`DE405`, `DE200`, `JPL-Horizons`) and bundled `splatalogue` spectral line tables are static runtime data that are **never touched** by the daily measures cron (remaining unchanged since 2021).
* **Casacore path requirements**: Casacore C++'s internal ephemeris engine (`MeasJPL`) queries `measurespath/ephemerides` directly for planetary and solar system body coordinates (e.g. Mars, Uranus, Sun, Titan calibrators).

To optimize I/O performance and disk footprint while guaranteeing complete astrometric accuracy, crash protection, and compatibility:
1. The pipeline **physically copies** `geodetic/` (~9.5 MB) to scratch, completely insulating active runs from NFS cron updates.
2. The pipeline **symlinks** `ephemerides/` and any other static directories (`alma/`, `catalogs/`, `nrao/`, etc.) from the source repository. This satisfies Casacore C++ table lookups, prevents `casaconfig` validation warnings (`casarundata is invalid`), and adds zero disk overhead. If symlink creation fails (e.g. due to filesystem limitations), `ephemerides/` automatically falls back to a physical copy.

This yields a tiny **~9.5 MB** copy payload per process that completes in **< 0.05 seconds**.

### 2. Shared-Nothing Multi-Process Concurrency

In parallel cluster executions (`mpicasa` or multi-worker pipelines), multiple processes frequently execute concurrently on the same compute host. Sharing a single scratch directory across processes would re-introduce file-locking contention and cleanup race conditions.

The staging mechanism uses a **Shared-Nothing** design:

```python
folder_name = f"casarundata_{user}_{job_id}_{pid}" if job_id else f"casarundata_{user}_{pid}"
target_dir = os.path.join(base_dir, folder_name)
```

* **Zero Lock Contention**: Every worker process operates on its own disjoint directory. There is zero lock contention, no deadlocks, and no risk of reading partially written tables.
* **Safe Sibling Cleanup**: Each process registers an `atexit` hook (`shutil.rmtree`) targeting strictly its own directory. Python's `rmtree` safely unlinks the `ephemerides` symlink without touching the underlying source files.
* **Negligible Disk Footprint**: 16 concurrent MPI worker ranks on a single host consume only **~152 MB** ($16 \times 9.5\text{ MB}$) of scratch space, easily fitting into any `/tmp` `tmpfs` RAM disk (even 500 MB).

### 3. Unified In-Flight Redirection & Bootstrapping Strategy

To ensure robust measures table resolution across all execution environments (modular Python, monolithic interactive CASA, MPI cluster execution), the pipeline employs a **unified two-phase synchronization strategy**:

1. **Early Staging (`pipeline.config`)**:
   * `stage_local_measures()` executes when `pipeline.config` is loaded (at the top of `pipeline/__init__.py`), before `domain`, `environment`, or `infrastructure` import CASA.
   * Setting `casaconfig.config.measurespath` and disabling auto-updates before `casatools` imports protects modular Python (`bin/python3`) from network auto-update collisions or filesystem contention on shared NFS mounts during `casatools/__init__.py` module initialization.
   * Because `casatools` only evaluates `casaconfig.config` once upon initial import, pre-configuring `casaconfig` ensures clean startup.
   * **Why it cannot live in `pipeline.environment` or `pipeline.infrastructure`**: `environment.py` imports `casatasks`, and `infrastructure.logging` imports `from casatasks import casalog` at module level. `casatasks/__init__.py` unconditionally imports `from casatools import logsink`, which would prematurely import `casatools` before staging can run.

2. **Unified In-Flight C++ Redirection (`ctsys.setmeasurespath` / `ctsys.setpath`)**:
   * After CASA modules are imported, `casatasks_startup()` unconditionally synchronizes the C++ runtime:
     ```python
     casatools.ctsys.setmeasurespath(staged_path)
     casatools.ctsys.setpath([staged_path] + [p for p in curr_path if p != staged_path])
     ```
   * These C++ methods directly update `casatools::State::setDistroDataPath()` and `casatools::State::setDataPath()` in memory under mutex protection.
   * This unified in-flight call eliminates special-case branching between modular and monolithic CASA (`bin/casa` / `mpicasa`): both environments execute the exact same instructions and bind casacore's runtime resolver to the node-local scratch tables.

### 4. Resilient Fallback

If the target scratch filesystem is read-only, full, or unwritable, the pipeline catches the exception, outputs a stderr warning, and gracefully falls back to the original shared measures directory without halting execution.

---

## Batch & Cluster Environment Integration

The staging mechanism inspects environment variables to locate the fastest, scheduler-isolated scratch storage:

### Scratch Base Directory Resolution Order

1. `config['pipeconfig']['local_measures_base']` (from `config.yaml`)
2. `$PIPELINE_LOCAL_MEASURES_BASE` (custom environment override)
3. `$SLURM_TMPDIR` (Slurm node-local NVMe / RAM scratch)
4. `$_CONDOR_SCRATCH_DIR` / `$CONDOR_SCRATCH_DIR` (HTCondor execute directory)
5. `$TMPDIR` (POSIX standard temporary storage)
6. `/tmp` (system default fallback)

### Dynamic Measures Source Discovery

The source repository is auto-discovered without requiring hardcoded system paths:

1. Caller argument / `pipeconfig.local_measures_source`
2. `$PIPELINE_LOCAL_MEASURES_SOURCE`
3. `$CASADATA`
4. `casaconfig.config.measurespath`
5. `casatools.ctsys.measurespath()` / `ctsys.rundata()`
6. `casaconfig.config.datapath`

---

## Configuration Reference

### Enabling via Pipeline Configuration (`config.yaml`)

Local measures staging can be configured in `pipeline/config.yaml` or user/session override files (`~/.casa/config.yaml` or `./config.yaml`):

```yaml
pipeconfig:
  stage_local_measures: true       # Enable node-local measures staging (default: false)
  local_measures_source: null      # Custom source measures directory (null = auto-discover)
  local_measures_base: null        # Custom scratch base directory (null = auto-detect)
  cleanup_local_measures: true     # Automatically purge on exit (default: true)
```

### Enabling via Environment Variables

For automated regression test scripts, Slurm sbatch scripts, or HTCondor submit files, staging can be toggled via environment variables without modifying configuration files:

```bash
# Enable node-local measures staging
export PIPELINE_STAGE_LOCAL_MEASURES=true

# Optional: route to a specific fast scratch disk
export PIPELINE_LOCAL_MEASURES_BASE=/var/tmp

# Optional: explicitly specify the source repository
export PIPELINE_LOCAL_MEASURES_SOURCE=/lustre/shared/casa-data

# Optional: retain staged tables after process exit for inspection
export PIPELINE_CLEANUP_LOCAL_MEASURES=false
```

---

## OS Retention and Cleanup Considerations

On Linux distributions (RHEL, Rocky, CentOS), `/tmp` is managed by `systemd-tmpfiles-clean.service` with a default retention policy of **10 days** (`/var/tmp` defaults to **30 days**). Because CASA tasks actively access geodetic tables throughout execution, file access timestamps (`atime`) are continually refreshed, preventing premature OS deletion during long pipeline runs.

When executing under batch schedulers (Slurm or HTCondor), `$SLURM_TMPDIR` and `$_CONDOR_SCRATCH_DIR` reside in scheduler-managed job scratch space that is exempt from `systemd-tmpfiles` and is automatically purged upon job completion.
