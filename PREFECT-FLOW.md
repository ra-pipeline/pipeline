### Adding Prefect Job Management to the Single Dish Pipeline
Adding `prefect` to a data pipeline is relatively straight-forward and is outlined in more detail in the 
official [documentation](https://docs.prefect.io/v3/get-started/quickstart#open-source); here I will give 
a simple overview related to my implementation in the single dish pipeline script on the `pipeline` branch
[prefect-sd-experiment](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/compare/commits?sourceBranch=refs%2Fheads%2Fprefect-sd-experiment&targetBranch=refs%2Fheads%2Fprefect_demo).
 In summary, a simple implementation on `prefect` in your code is as simple as wrapping your pipeline tasks in 
the `@task` decorator and wrapping your pipeline script in the `@flow` decorator.

#### Added Dependencies

A few packages are needed to get things up and running for the `pipeline` codes. In this example, I will use 
the `mamba` pacakge and environment manager to build a clean coding environment and give a list of the required 
libraries; as a note, the commands are exactly the same for `conda` or `miniconda`.

Building the environment.
```angular2html
mamba create --name prefect python=3.13 
mamba activate prefect
```

You will also need a copy of `casa`. In my example I am using the minimum modular casa tasks, I had issues running 
`prefect` using the monolithic build. For my environment I have the following modular casa modules.

```angular2html
python -m pip list |grep casa

casaconfig                         1.4.0
casaplotms                         2.7.4
casatasks                          6.7.2.42
casatools                          6.7.2.42
casashell                          6.7.2.42
```

These should match the `pipeline` branch that is being used for the example. In addition, I am using `prefect 3.6.2` and
`protobuf 3.20.2`. The latter is important as `casa` seems to be compiled with an older version of `protobuf` and will 
not work with the modern version that gets install otherwise. After downloading the `pipeline` branch code.

```
cd /pipeline-branch/
python -m pip install -r requirements.txt
python -m pip install -e .

python -m pip install prefect casaplotms==2.7.4 casatasks==6.7.2.42 casatools==6.7.2.42 protobuf==3.20.3
```

#### Changes to Module Functions
As explained about adding a pipeline function to the tasks handled by prefect is simple. As an example let's 
look at the beginning of the `hsd.py` module from the single dish cli.

```angular2html

import traceback

# Pipeline imports
import pipeline
from pipeline.infrastructure import casa_tools

from prefect import flow

# Make pipeline tasks available in local name space
pipeline.initcli(locals())

IMPORT_ONLY = 'Import only'

ITERATION = 2


# Run the procedure
@flow
def hsdms(vislist, importonly=False, interactive=True):
    ... hsdm code ...
```

Here we have added two things: we have added the import of the `prefect.task` decorator and have then added it 
to the `hsdm(...)` function. That is all there is to it. Do this for every function that will be handled in the 
pipeline that `prefect` will be managing.

#### Changes to Pipeline Scripts

The last step in the process of the simple `prefect` implementation is to modify our pipeline script. For this
example I chose to use the following pipeline script which I have included in the case that the user doesn't have
copy.

```angular2html
import glob
import pipeline

from pipeline.h.cli import h_init
from pipeline.h.cli import h_tsyscal
from pipeline.h.cli import h_save

from pipeline.hsd.cli import *

from prefect import flow

@flow
def replay():
    pipeline.initcli()

    __rethrow_casa_exceptions = True
    context = h_init()

    asdms = glob.glob('../rawdata/uid___A002_X*')
    asdms.sort()
    session = ['default' for _ in asdms]

    try:
        hsd_importdata(vis=asdms, session=session)
        hsd_flagdata()
        h_tsyscal()
        hsd_tsysflag()
        hsd_skycal()
        hsd_k2jycal()
        hsd_applycal()
        hsd_atmcor()
        hsd_baseline()
        hsd_blflag()
        hsd_baseline()
        hsd_blflag()
        hsd_imaging()
        hsd_exportdata()
    finally:
        h_save()

if __name__ == "__main__":
    replay()
```
As with the `@task` implementation, the script is edited with two lines of code. First adding the import statement
`from prefect import flow` and second by adding the `@flow` decorator to the `replay` function. As a note, this
script was adapted from one of the replay scripts included in the pipeline data and a few changes were required
due to the script assuming the user was using `casashell`. First the pipeline functions needed to be imported
individually and second the script needed to be wrapped in a callable function.

I have also included a version of this script in the base directory of the `pipeline` branch code as `casa_pipe_flow.py`.

#### Dashboard and Remote Monitoring

In the case of NAOJ, the dashboard needed to be monitored on a remote server where the code was being run. I thought
it would be useful to include a simple explanation of how to bring this dashboard up locally.

##### On the remote server:
With your environment activated,
```angular2html
(prefect) username@remote-server:~$ prefect server start
```
 You should see an output like the following.
```

 ___ ___ ___ ___ ___ ___ _____
| _ \ _ \ __| __| __/ __|_   _|
|  _/   / _|| _|| _| (__  | |
|_| |_|_\___|_| |___\___| |_|

Configure Prefect to communicate with the server with:

    prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api

View the API reference documentation at http://127.0.0.1:4200/docs

Check out the dashboard at http://127.0.0.1:4200
```
This means your remote prefect server is running. Take note of the dashboard address and the port number.

##### On your local machine:

Locally you want to now open an ssh connection with the port forwarded.

```angular2html
(base) username@local-machine ~/ $ ssh -L 4200:localhost:4200 username@remote-server
```

You should now be able to paste the dashboard address into your favorite web browser and see the dashboard running.

#### Data Retrieval

You can get a copy of the data used for this study from the `toolviper` data repository.

```angular2html
python -m pip install toolviper

>>> import toolviper
>>> toolviper.utils.data.update()
>>> toolviper.utils.data.download(file="absolute_off", folder=".", overwrite=True)
```