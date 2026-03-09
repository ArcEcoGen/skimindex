#!/bin/bash
#OAR -n download_references
#OAR -l /nodes=1/core=10,walltime=48:00:00
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

G15x_HOME=/bettik/LECA/home/pan/G15X


cd ${G15x_HOME}
${G15x_HOME}/skimindex.sh download all
