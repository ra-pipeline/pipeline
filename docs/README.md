## Pipeline Docs

- run the following commands under docs/:
  
  ```console
  cd pipeline/docs/
  export casa_dir=/home/rxue/Workspace/local/nrao/casa_dist/casa-6.4.1-10-py36-sphinx
  ${casa_dir}/bin/pip3 --disable-pip-version-check install -r requirements_docs.txt
  # export pipeline_dir=/home/rxue/Resilio/Workspace/nrao/gitlab/pl_sphinx/pipeline
  make html # generate the html docs under ./pipleine/docs/html
  ```

  If the "apidoc" of CASA CLI bindings is wanted, try

  ```console
  ${casa_dir}/bin/python3 setup.py buildmytasks -i -j 10
  ```

  before building docs, install the Pipeline first.

pip install --use-pep517 -e .
