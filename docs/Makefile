# You can set these variables from the command line.
SPHINXOPTS    = -v -j auto
SPHINXBUILD   = ${casa_dir}/bin/python3 -msphinx
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
#	html:	for html (do not refresh the costly apidoc)
#	latex:	for latex
#	pdf:	for latex+pdf
#	docs:	for both html and latex+pdf
#

apidoc:
	@rm -rf ./source/_apidoc 
	@sphinx-apidoc -o ./source/_apidoc/ ../pipeline ../pipeline/recipes/*.py ../pipeline/run*pipeline.py

taskdocs:
	@rm -rf ./source/_taskdocs
	@${casa_dir}/bin/python3 source/create_docs/create_docs.py --outdir source/_taskdocs --inputdir ../


# for CI docs build (no ipynb copying)
docs:
	@make taskdocs
	@make apidoc
	@rm -rf html latex doctrees source/_autosummary
	@make html
	@rm -rf casa-*.log source/casa-*.log	

pdf:
	@make apidoc
	@rm -rf latex/*
	@make latexpdf