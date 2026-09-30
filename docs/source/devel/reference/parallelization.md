# Parallelization

* [pipeline/infrastructure/mpihelpers.py](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/mpihelpers.py) - This module contains the original `casampi`-based wrapper layer. It is used to dispatch {doc}`pipeline tasks <../../apisummary>`, casatasks [jobrequest](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/jobrequest.py), or any pickleable Python functions through `casampi` on the preallocated MPI cluster spawned from a `mpicasa` session.

* [pipeline/infrastructure/daskhelpers.py](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/daskhelpers.py) - This module contains helper functions, including the logic for sanitizing MPI environment variables to prevent conflicts when running Dask workers within an active MPI session. It also includes utilities for creating and configuring Dask clusters with different backends (local, Slurm, HTCondor, Kubernetes) and for handling the lifecycle of the cluster in the context of the pipeline. It provides a Dask-based mechanism to dispatch pipeline tasks, casatasks `jobrequest`, or pickleable Python functions, serving as an alternative to the `casampi`-based approach in `mpihelpers.py`.

* [pipeline/infrastructure/parslhelpers.py](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/parslhelpers.py) - This module provides the Parsl adaptation layer for pipeline task dispatch. It checks DataFlowKernel readiness, routes Tier0 executables to targeted executors (such as `tier0_executor`), handles working directory restoration for remote batch workers, and merges worker CASA command logs back into the client session.

* [pipeline/config.yaml](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/config.yaml) - The default configuration file where Dask cluster settings are defined, including parameters for different cluster types, default worker counts, and job names. A hierarchical structure configuration setup is implemented (`workdir/config.yaml`->`~/.casa/config.yaml`->`pipeline/config.yaml`) to allow for flexible overrides at different levels of the user environment. This is the current setup for Dask cluster parameters.

## Parsl Adaptation Layer

The Parsl adaptation layer (`pipeline.infrastructure.parslhelpers`) enables the CASA pipeline to dispatch parallel Tier0 workloads—such as calibrator imaging (`tclean`), RMS map generation (`imdev`), and batched plot generation (`plotms`)—to workers managed by Parsl.

### Design and Touchpoints

The pipeline uses an abstract `Executable` pattern to decouple heuristics from the underlying execution engine. When Parsl is loaded and active, task factories encapsulate work in a `Tier0Executable` and pass it to `parslhelpers.ParslTask`.

```mermaid
flowchart TD
    subgraph ClientProcess ["Client Python Process"]
        TF["Task Factory / TaskQueue<br>(makeimages, sessionutils, mpihelpers)"]
        PH["parslhelpers.ParslTask"]
        DFK["Parsl DataFlowKernel (DFK)"]
        LogMerge["Log Merger<br>(_merge_casa_commands)"]
    end

    subgraph ParslWorkerPool ["Parsl Worker Pool"]
        T0Exec["tier0_executor<br>(Compute tasks: 32GB)"]
        WLExec["weblog_executor<br>(Rendering tasks: 8GB)"]
    end

    subgraph RemoteWorker ["Worker Process"]
        PApp["parsl_exec()"]
        Chdir["os.chdir(working_dir)"]
        RunExec["executable()"]
        CmdLog["casa_commands_tier0.log"]
    end

    TF -->|"parslhelpers.is_parsl_ready()"| PH
    PH -->|"get_parsl_exec(app_name)"| DFK
    DFK -->|"executors=['tier0_executor']"| T0Exec
    T0Exec -->|"Submits task"| PApp
    PApp --> Chdir
    Chdir --> RunExec
    RunExec --> CmdLog
    PApp -->|"Returns result + logs"| PH
    PH --> LogMerge
    LogMerge -->|"Appends to"| ClientCmdLog["casa_commands.log"]
```

Key touchpoints across the pipeline architecture:
- `is_parsl_ready()`: Evaluates `parsl.dfk()` existence and ensures `dfk.cleanup_called` is false.
- `get_parsl_exec(app_name)`: Cached via `_PARSL_APPS` keyed by `(id(dfk), app_name)`. Dynamically targets `tier0_executor` when present in the DFK, falling back to `'all'` for single-pool clusters.
- `ParslTask`: Wraps task submission to Parsl, capturing the current working directory (`os.getcwd()`), awaiting results on `.get_result()`, and triggering `_merge_casa_commands`.
- `TaskQueue` & `CleanTaskFactory`: Prioritizes dispatch order as `Parsl` -> `Dask` -> `MPI` -> `Serial`.

### Trade-offs and Considerations

- **Multi-pool Resource Matching**: Unlike MPI (which uses a uniform pool of pre-spawned ranks), Parsl allows concurrent heterogeneous pools (e.g. `tier0_executor` with large memory for tclean vs `weblog_executor` for rendering). Explicit executor targeting ensures high-memory tasks do not starve or crash lightweight worker pods.
- **Worker Execution Context**: Batch schedulers (such as HTCondor) execute jobs within transient scratch directories. Workers explicitly change directories back to the project root (`working_dir`) upon invocation to allow relative file paths to MeasurementSets and calibration tables to resolve.
- **Log Isolation and Merging**: Each worker produces its own slice of CASA command logs. The client process reconciles `casa_commands_tier0.log` into the main `casa_commands.log` upon task completion, maintaining linear command histories.
- **Process Isolation vs. Thread Safety**: CASA C++ extensions are not thread-safe. Parsl execution must always utilize multiprocessing or process-isolated providers (such as `HighThroughputExecutor`) rather than `ThreadPoolExecutor`.

### Guidelines for Developers

- **Precedence Order**: When implementing new parallel task factories, always check backends in standard precedence order:
  ```python
  if parallel_wanted and parslhelpers.is_parsl_ready():
      return parslhelpers.ParslTask(executable)
  elif parallel_wanted and daskhelpers.is_dask_ready():
      return daskhelpers.FutureTask(executable)
  elif parallel_wanted and mpihelpers.is_mpi_ready():
      return mpihelpers.AsyncTask(executable)
  else:
      return mpihelpers.SyncTask(sync_call, executor)
  ```
- **Direct Function Invocation**: Call `parslhelpers.is_parsl_ready()` directly. Do not wrap with defensive `getattr(..., lambda: False)` checks.
- **State Serialization**: Ensure all task parameters encapsulated in `Tier0Executable` are picklable by standard Python pickle. Context state must be saved to `.context` temporary files rather than serialized wholesale over RPC.

## Future improvement - Potential Parallelization Paradigm for Pipeline processing

## version 1

* with traditional `mpicasa` configuration, no nested subprocess, dask clusters spawned from the mpi client process
* mpi cluster is still a fixed resource allocation.

```mermaid
graph TD
    %% ===============================
    %% CASA OpenMPI Session
    %% ===============================
    subgraph OpenMPI_System["CASA OpenMPI Session"]
        mpiclient((mpiclient))
        mpiserver1(mpiserver1)
        mpiserver2(mpiserver2)
        mpiserver3(mpiserver3)
        
        %% Communication between client and servers
        mpiclient <--> mpiserver1
        mpiclient <--> mpiserver2
        mpiclient <--> mpiserver3
    end

    %% ===============================
    %% Dask Cluster
    %% ===============================
    subgraph DaskCluster["Dask Cluster"]
        daskworker1(daskworker1)
        daskworker2(daskworker2)
        daskworker3(daskworker3)
    end

    %% Connections between MPI client and Dask workers
    mpiclient <--> daskworker1
    mpiclient <--> daskworker2
    mpiclient <--> daskworker3

    %% ===============================
    %% Worker Backend Types
    %% ===============================
    subgraph Worker_Backends["Possible Worker Backends"]
        localproc(Local Processes)
        slurm(Slurm Jobs)
        htcondor(HTCondor Jobs)
        k8s(Kubernetes Pods)
    end

    %% DaskCluster connects to all backend types
    DaskCluster --> localproc
    DaskCluster --> slurm
    DaskCluster --> htcondor
    DaskCluster --> k8s
```

## version 2

* parallelization/workflow/graphreduction handled by Dask and workflow orchestration library,
* with nested subprocess for casampi / tclean(parallel=True) if absolutely necessary when no alternative solution exists, such as [CASA memo#13](https://casadocs.readthedocs.io/en/stable/notebooks/memo-series.html).
* data processing session reaches out to workload manager / resource manager for surged resource allocation, instead of fixed resource allocation at the start of the session.
* persisted new context design with adaptation layer to support existing pipeline framework and new parallelization/workflow paradigm.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#fff4dd', 'edgeLabelBackground':'#ffffff', 'tertiaryColor': '#f4f4f4', 'clusterBkg': '#fafafa', 'clusterBorder': '#eeeeee'}}}%%
graph TB



    %% Start Node
    Start((Start Session: Python/CASA)) --> St1_Node

    %% === STAGE 1 ROW ===
    subgraph Row1 [Stage 1]
        direction LR
        St1_Node[<b>Heuristics+</br>LocalCluster</b>]
        D1_Sched[Dask Scheduler]
        D1_Work{{Local Processes as Workers}}
        D1_Job[[Standard Tasks<br>Tier0-subtasks<br>Python Functions]]

        St1_Node -- 1. Spawns --> D1_Sched
        D1_Sched -- 2. Manages --> D1_Work
        D1_Work -- 3. Runs --> D1_Job
    end

    %% Link Stage 1 to Stage 2
    St1_Node --> St2_Node

    %% === STAGE 2 ROW ===
    subgraph Row2 [Stage 2]
        direction LR
        St2_Node[<b>Heuristics</br>SLURMCluster, or</br>PrefectDask+SLURMCluster</b>]
        D2_Sched[Dask Scheduler]
        D2_Work{{Slurm Jobs as Workers}}

        %% THE CHANGE: Nested Subgraph for Python Process -> Casampi
        subgraph PyProc [Python SubProcess]
            direction TB
            %% Optional style to make the outer box look distinct (e.g., white background)
            style PyProc fill:#dcedc8,stroke:#333,stroke-width:2px
            
            Casampi[<b>Casampi Session</b><br>tclean/parallel=True]
        end

        St2_Node -- 1. Submits --> D2_Sched
        D2_Sched -- 2. Allocates --> D2_Work
        D2_Work -- 3. Runs --> Casampi
    end

    %% Link Stage 2 to Stage 3
    St2_Node --> St3_Node

    %% === STAGE 3 ROW ===
    subgraph Row3 [Stage 3]
        direction LR
        St3_Node[<b>Heuristics</br>KubeCluster</b>]
        D3_Sched[Dask Scheduler]
        D3_Work{{K8s GPU Pods}}
        D3_Job[[GPU Acceleration Jobs]]

        St3_Node -- 1. Requests --> D3_Sched
        D3_Sched -- 2. Orchestrates --> D3_Work
        D3_Work -- 3. Runs --> D3_Job
    end

    %% Link Stage 2 to Stage 3
    St3_Node --> St4_Node

    %% === STAGE 4 ROW ===
    subgraph Row4 [Stage 4]
        direction LR
        St4_Node[<b>Heuristics+</br>PrefectKubernetes/Worker</b>]
        D4_Sched[Worker Pool]
        D4_Work{{K8s GPU Pods}}
        D4_Job[[GPU Acceleration Jobs]]

        St4_Node -- 1. Requests --> D4_Sched
        D4_Sched -- 2. Orchestrates --> D4_Work
        D4_Work -- 3. Runs --> D4_Job
    end    

    %% End Node
    St4_Node --> End((End Session))
    class St1_Node,St2_Node,St3_Node,St4_Node stageNode;
    %% === STYLING ===
    classDef stageNode fill:#ffccbc,stroke:#bf360c,stroke-width:2px,color:black;
    class St1_Node,St2_Node,St3_Node stageNode;

    classDef dask fill:#e1f5fe,stroke:#0277bd,stroke-width:1px;
    class D1_Sched,D2_Sched,D3_Sched,D1_Work,D2_Work,D3_Work dask;

    classDef jobs fill:#dcedc8,stroke:#33691e,stroke-width:1px;
    class D1_Job,D2_Job,D3_Job jobs;
```
