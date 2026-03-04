#!/bin/bash
#OAR -n download_partial_gb
#OAR -l /nodes=1/core=32,walltime=4:00:00
#OAR --project phyloalps
#OAR -O %jobname%.%jobid%.stdout
#OAR -E %jobname%.%jobid%.stderr

# This job download a few division of genbank useful
# to setup genome cleaning by tagging :
#   - bacterial,
#   - human,
#   - fungal
# sequences
#
# Use the commands to run the job
#
# cd /bettik/LECA/home/pan/G15X/genbank
# oarsub -S ./genbank_download.sh

export PATH=/bettik/LECA/ENVIRONMENT/softs/obitools4/bin:$PATH
#obik index --entropy-filter 0.5 --index-id plants Plants/ --out /silenus/PROJECTS/pr-phyloalps/COMMON/G15x/Contaminent_idx
obik index --entropy-filter 0.5 --index-id human Human/ --out /silenus/PROJECTS/pr-phyloalps/COMMON/G15x/Contaminent_idx
