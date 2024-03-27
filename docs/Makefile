# You can set these variables from the command line.

# if you use CASA interpreter, set env:pythonbin first, e.g,
#	export pythonbin=${casa_dir}/bin/python3
PYTHON := $(if $(pythonbin),$(pythonbin),python3)

SPHINXOPTS    = -v -j auto
SPHINXBUILD   = ${PYTHON} -msphinx
#SPHINXOPTS    = -v -j auto -b coverage
SPHINXPROJ    = pipeline_docs
SOURCEDIR     = source
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# options:
#
#	html:			for html (do not refresh the costly apidoc)
#	latex:			for latex
#	pdf:			for latex+pdf
#	docs:			for both html and latex+pdf
#	pdf_taskdocs: 	make the Pipeline task reference manual pdf file: _build/latex/taskdocs.pdf

apidoc:
	@rm -rf ./source/_apidoc 
	@sphinx-apidoc -o ./source/_apidoc/ ../pipeline ../pipeline/recipes/*.py ../pipeline/run*pipeline.py


taskapidoc: 
	@rm -rf ./source/_apidoc 
	@sphinx-apidoc -o ./source/_apidoc/ ../pipeline ../pipeline/recipes/*.py ../pipeline/run*pipeline.py ../pipeline/domain/*.py ../pipeline/extern/*.py ../pipeline/infrastructure/*.py ../pipeline/qa/*.py ../pipeline/h*/heuristics/*.py ../pipeline/h*/tasks/*.py ../pipeline/h*/templates/*.py ../pipeline/h*/environment/*.py


taskdocs:
	@rm -rf ${SOURCEDIR}/_taskdocs
	@${PYTHON} ./source/pipeline_tasks/create_docs.py --outdir ${SOURCEDIR}/_taskdocs --srcdir ../

html_docs:
	@make taskdocs
	@make apidoc
	@rm -rf ${BUILDDIR}/html ${BUILDDIR}/doctrees ${SOURCEDIR}/_autosummary
	@make html
	@rm -rf casa-*.log ${SOURCEDIR}/casa-*log

pdf_taskdocs:
	@make taskdocs
	@rm -rf ${BUILDDIR}/latex ${BUILDDIR}/doctrees
	@make latexpdf
	@rm -rf casa-*.log ${SOURCEDIR}/casa-*log
