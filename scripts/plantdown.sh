#!/bin/bash
#OAR -n plantdown
#OAR -l /nodes=1/core=2,walltime=48:00:00
#OAR --project phyloalps
#OAR -O %jobname%.%jobid%.stdout
#OAR -E %jobname%.%jobid%.stderr

cd /bettik/LECA/home/pan/G15X

bin/datasets download genome taxon Spermatophyta --assembly-level complete --include gbff --assembly-version latest --filename genbank/spermatophyta_gbff.zip
