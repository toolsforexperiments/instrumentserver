# Minimal makefile for Sphinx documentation

# You can set these variables from the command line.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
PAPER         ?=
BUILDDIR      ?= build

# User-friendly check for sphinx-build
ifeq ($(shell which $(SPHINXBUILD) >/dev/null 2>&1; echo $$?), 1)
$(error The '$(SPHINXBUILD)' command was not found. Make sure you have Sphinx installed, then set the SPHINXBUILD environment variable to point to the actual 'sphinx-build' executable. Alternatively you can add a directory to the PATH environment variable so that the '$(SPHINXBUILD)' executable is found.)
endif

# Internal variables.
PAPEROPT_a4     = -D latex_paper_size=a4
PAPEROPT_letter = -D latex_paper_size=letter
ALLSPHINXOPTS   = -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) .
# the i18n builder cannot share the output directory and doctrees with the other builders
I18NSPHINXOPTS  = $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) .

.PHONY: help Makefile

# Put it first so that "make" without argument is still useful for quick reference.
help:
	@$(SPHINXBUILD) -M help $(ALLSPHINXOPTS)

.PHONY: help Makefile
%: Makefile
	@$(SPHINXBUILD) -M $@ $(ALLSPHINXOPTS) $(BUILDDIR)

clean:
	rm -rf $(BUILDDIR)
	rm -rf api/generated