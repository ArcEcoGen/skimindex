#!/bin/bash
#OAR -n fungigrep
#OAR -l /nodes=1/core=8,walltime=48:00:00
#OAR --project phyloalps
#OAR -O %jobname%.%jobid%.stdout
#OAR -E %jobname%.%jobid%.stderr

# This job get fungi sequences out of plant division
#
# Use the commands to run the job
#
# cd /bettik/LECA/home/pan/G15X/genbank/Release_269.0/fasta/pln/
# oarsub -S ./genbank_download.sh

export PATH=/bettik/LECA/ENVIRONMENT/softs/obitools4/bin:$PATH
cd /bettik/LECA/home/pan/G15X/genbank/Release_269.0/fasta/pln/

obigrep -t ../../ncbitaxo.tgz -r taxon:4751 \
       --update-taxid \
       --no-order \
       -Z \
       /bettik/LECA/home/pan/G15X/genbank/Release_269.0/fasta/pln \
       > all_fungi.fasta.gz
