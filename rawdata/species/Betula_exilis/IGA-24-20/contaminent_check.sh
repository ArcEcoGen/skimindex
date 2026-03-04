#!/bin/bash
#OAR -n Contaminent_check
#OAR -l /nodes=1/core=192,walltime=4:00:00
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
obik match -Z \
           --index /hoyt/PROJECTS/pr-phyloalps/coissac/G15x/Contaminent_idx \
           59-IGA-24-20_S96_L001_R1_001_nolow.fastq.gz \
           > xxx.fasta.gz
