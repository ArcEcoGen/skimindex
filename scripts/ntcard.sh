#!/bin/bash
#OAR -n kmer_counting
#OAR -l /nodes=1/core=32,walltime=24:00:00
#OAR --project phyloalps
#OAR -O %jobname%.%jobid%.stdout
#OAR -E %jobname%.%jobid%.stderr

. /applis/environments/conda.sh
export PATH="/bettik/LECA/home/pan/G15X/bin:$PATH"
export PATH=/bettik/LECA/ENVIRONMENT/softs/obitools4/bin:$PATH
conda activate G15x

BASE=/bettik/LECA/home/pan/G15X/genbank



# Human

echo "[$(date)] Starting human kmer counting..."

ntcard -k 31 -t 8 -o ${BASE}/Human/human_kmer_spectrum.txt ${BASE}/Human/human_genome.fasta.gz 2>&1 | head -2 > ${BASE}/Human/human_kmer_stats.txt



# Plants

echo "[$(date)] Starting plant kmer counting..."

ntcard -k 31 -t 8 -o ${BASE}/Plants/plants_kmer_spectrum.txt ${BASE}/Plants/plant_genomes.fasta.gz 2>&1 | head -2 > ${BASE}/Plants/plants_kmer_stats.txt

# Fungi

echo "[$(date)] Starting fungi kmer counting..."

ntcard -k 31 -t 8 -o ${BASE}/Fungi/fungi_kmer_spectrum.txt ${BASE}/Fungi/all_fungi.fasta.gz 2>&1 | head -2 > ${BASE}/Fungi/fungi_kmer_stats.txt



# Bacteria (最大，给最多线程，最后跑)

echo "[$(date)] Starting bacteria kmer counting..."

ntcard -k 31 -t 30 -o ${BASE}/Release_269.0/fasta/bct/bct_kmer_spectrum.txt ${BASE}/Release_269.0/fasta/bct/*.fasta.gz 2>&1 | head -2 > ${BASE}/Release_269.0/fasta/bct/bct_kmer_stats.txt



echo "[$(date)] All done!"
