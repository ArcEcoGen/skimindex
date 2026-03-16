#!/bin/bash
#OAR -n split_references
#OAR -l /nodes=1/core=32,walltime=48:00:00
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

. /bettik/LECA/home/pan/G15X/etc/G15x_env.bash
./skimindex.sh split
