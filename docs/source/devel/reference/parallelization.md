# Parallelization

* [pipeline/infrastructure/mpihelpers.py](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/mpihelpers.py) - This module contains the original `casampi`-based wrapper layer. It is used to dispatch {doc}`pipeline tasks <../../apisummary>`, casatasks [jobrequest](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/jobrequest.py), or any pickleable Python functions through `casampi` on the preallocated MPI cluster spawned from a `mpicasa` session.

* [pipeline/infrastructure/daskhelpers.py](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/daskhelpers.py) - This module contains helper functions, including the logic for sanitizing MPI environment variables to prevent conflicts when running Dask workers within an active MPI session. It also includes utilities for creating and configuring Dask clusters with different backends (local, Slurm, HTCondor, Kubernetes) and for handling the lifecycle of the cluster in the context of the pipeline. It provides a Dask-based mechanism to dispatch pipeline tasks, casatasks `jobrequest`, or pickleable Python functions, serving as an alternative to the `casampi`-based approach in `mpihelpers.py`.

* [pipeline/config.yaml](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/config.yaml) - The default configuration file where Dask cluster settings are defined, including parameters for different cluster types, default worker counts, and job names. A hierarchical structure configuration setup is implemented (`workdir/config.yaml`->`~/.casa/config.yaml`->`pipeline/config.yaml`) to allow for flexible overrides at different levels of the user environment. This is the current setup for Dask cluster parameters.

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
