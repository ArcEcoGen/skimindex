#!/bin/bash

# Install the conda environment on Gricad
. /applis/environments/conda.sh

# Add the G15x script and binary directory to the path
export PATH="/bettik/LECA/home/pan/G15X/bin:$PATH"
export PATH=/bettik/LECA/ENVIRONMENT/softs/obitools4/bin:$PATH

# Ensure group write and eventually execute permisson on new files and directories
umask 002

# Launch an interactive job for 3 hours on 10 CPU
alias G15x_interactive='oarsub -I -l "nodes=1/core=10,walltime=03:00:00" -n "interactive session" --project phyloalps'

# Activate the conda environment (actually useless as it is automatically activated
alias condaenv='. /applis/environments/conda.sh'
alias G15x_conda='conda activate G15x'

# The two next alias are for facilitate sharing of G15x environment among us
#  - G15x_export: export our current G15x environment
#  - G15x_update: update our G15x environment from the latest export (done using G15x_update)
alias G15x_export='conda env export --name G15x --file /bettik/LECA/home/pan/G15X/share/G15x_conda.yml'
alias G15x_update='conda env update --name G15x --file /bettik/LECA/home/pan/G15X/share/G15x_conda.yml --prune'

alias G15x_go='cd /bettik/LECA/home/pan/G15X'
alias G15x_pushd='pushd /bettik/LECA/home/pan/G15X'
