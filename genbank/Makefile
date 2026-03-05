SHELL := /bin/bash

FTPNCBI       := ftp.ncbi.nlm.nih.gov
GBURL         := https://$(FTPNCBI)/genbank
GBRELEASE_URL := $(GBURL)/GB_Release_Number
TAXOURL       := https://$(FTPNCBI)/pub/taxonomy/taxdump.tar.gz

# ---------- release number -----------------------------------------
# One small request (~100 bytes) — unavoidable to know the release.
GBRELEASE := $(shell curl -s $(GBRELEASE_URL))

# ---------- FTP directory listing (cached per release) -------------
# The listing is downloaded once and stored locally.
# All subsequent variable derivations read from this local file,
# so re-running make never triggers additional network requests.
GB_LISTING := Release_$(GBRELEASE)/.gb_listing

# Side-effect assignment: create the cache file if it does not exist.
# Evaluated at parse time (`:=`), before GBDIV_ALL / GBFILE_ALL below.
_ := $(shell \
    if [ ! -f "$(GB_LISTING)" ]; then \
        mkdir -p "$(dir $(GB_LISTING))" && \
        curl -s -L "$(GBURL)" > "$(GB_LISTING)" && \
        echo "[cache] FTP listing saved: $(GB_LISTING)" >&2; \
    fi)

# ---------- division lists (derived from local cache) --------------
empty :=
space := $(empty) $(empty)

# All divisions present in the current release (parsed from filenames).
GBDIV_ALL := $(shell sed -nE 's/.*gb([a-z]+)[0-9]+\.seq\.gz.*/\1/p' \
                 $(GB_LISTING) | sort -u)

# Divisions to download (override on the command line if needed).
# To clean genome skim against contaminations from:
#   - Bacteria: bct
#   - Fungi: pln
GBDIV := bct pln
# GBDIV := bct inv mam phg pln pri rod vrl vrt

# ERE alternation pattern built from GBDIV (e.g. "bct|pln").
GBDIV_PATTERN := $(subst $(space),|,$(GBDIV))

# All matching filenames for the selected divisions.
GBFILE_ALL := $(shell grep -oE 'gb($(GBDIV_PATTERN))[0-9]+\.seq\.gz' \
                  $(GB_LISTING))

# ---------- dependency / stamp infrastructure ----------------------
DIRECTORIES := fasta fasta_fgs

SUFFIXES  += .d
NODEPS    := clean taxonomy
DEPFILES  := $(wildcard Release_$(GBRELEASE)/depends/*.d)

# Explicitly set the default goal before -include so that the first
# rule in a generated .d file does not become the default target.
.DEFAULT_GOAL := all

ifeq (0, $(words $(findstring $(MAKECMDGOALS), $(NODEPS))))
    -include $(DEPFILES)
endif

# ---------- top-level targets -------------------------------------
all: depends directories FORCE
	@make downloads

downloads: taxonomy fasta_files
	@echo Genbank Release number $(GBRELEASE)
	@echo all divisions : $(GBDIV_ALL)

FORCE:

.PHONY: all directories depends taxonomy fasta_files FORCE

depends: directories Release_$(GBRELEASE)/depends/gbfiles.d Makefile

division: $(GBDIV)

taxonomy: directories Release_$(GBRELEASE)/taxonomy

directories: Release_$(GBRELEASE)/fasta Release_$(GBRELEASE)/stamp Release_$(GBRELEASE)/tmp

# ---------- directory creation ------------------------------------
Release_$(GBRELEASE):
	@mkdir -p $@
	@echo Create $@ directory

Release_$(GBRELEASE)/fasta: Release_$(GBRELEASE)
	@mkdir -p $@
	@echo Create $@ directory

Release_$(GBRELEASE)/stamp: Release_$(GBRELEASE)
	@mkdir -p $@
	@echo Create $@ directory

Release_$(GBRELEASE)/tmp: Release_$(GBRELEASE)
	@mkdir -p $@
	@echo Create $@ directory

# ---------- dependency file generation ----------------------------
Release_$(GBRELEASE)/depends/gbfiles.d: Makefile
	@echo Create depends directory
	@mkdir -p Release_$(GBRELEASE)/depends
	@for f in ${GBFILE_ALL} ; do \
	            echo -e "Release_$(GBRELEASE)/stamp/$$f.stamp:" ; \
				echo -e "\t@echo Downloading file : $$f..." ; \
				echo -e "\t@mkdir -p Release_$(GBRELEASE)/tmp" ; \
				echo -e "\t@mkdir -p Release_$(GBRELEASE)/stamp" ; \
				echo -e "\t@curl -L ${GBURL}/$$f > Release_$(GBRELEASE)/tmp/$$f && touch \$$@"  ; \
				echo ; \
				div=$$(sed -E 's@^gb(...).*$$@\1@' <<< $$f) ; \
				fasta="Release_$(GBRELEASE)/fasta/$$div/$${f/.seq.gz/.fasta.gz}" ; \
				fasta_fgs="Release_$(GBRELEASE)/fasta_fgs/$$div/$${f/.seq.gz/.fasta.gz}" ; \
				fasta_files="$$fasta_files $$fasta" ; \
				fasta_fgs_files="$$fasta_fgs_files $$fasta_fgs" ; \
				echo -e "$$fasta: Release_$(GBRELEASE)/stamp/$$f.stamp" ; \
				echo -e "\t@echo converting file : \$$< in fasta" ; \
				echo -e "\t@mkdir -p Release_$(GBRELEASE)/fasta/$$div" ; \
				echo -e "\t@obiconvert -Z --fasta-output --skip-empty  \\" ; \
				echo -e "\t            Release_$(GBRELEASE)/tmp/$$f > Release_$(GBRELEASE)/tmp/$${f/.seq.gz/.fasta.gz} \\" ; \
				echo -e "\t            && mv Release_$(GBRELEASE)/tmp/$${f/.seq.gz/.fasta.gz} \$$@  \\" ; \
				echo -e "\t            && rm -f Release_$(GBRELEASE)/tmp/$$f  \\" ; \
				echo -e "\t            || rm -f \$$@" ; \
				echo -e "\t@echo conversion of $$@ done." ; \
				echo ; \
				done > $@ ; \
				echo >> $@ ; \
				echo "fasta_files: $$fasta_files" >> $@

# ---------- taxonomy ----------------------------------------------
Release_$(GBRELEASE)/taxonomy:
	@mkdir -p $@
	@cd $@ && obitaxonomy --download-ncbi
