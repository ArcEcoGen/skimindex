#!/bin/bash
#OAR -n index_human_genome
#OAR -l /nodes=1/core=10,walltime=1:00:00
#OAR --project phyloalps
#OAR -O %jobname%.%jobid%.stdout
#OAR -E %jobname%.%jobid%.stderr

. /bettik/LECA/home/pan/G15X/etc/G15x_env.bash

INDEX="human_test"
CATALOG="decontamination_test"
KMER_SIZE=29
N_PARTITIONS=10
N_CPU=${N_PARTITIONS}
G15x_HOME=/bettik/LECA/home/pan/G15X
G15x_FAST_HOME=/silenus/PROJECTS/pr-phyloalps/coissac/G15x
#G15x_FAST_HOME=/hoyt/PROJECTS/pr-phyloalps/coissac/G15x
UNIQ_KMER=$(awk '(NR==2) {print $NF}' $G15x_HOME/genbank/Human/human_kmer_stats.txt)

echo "Count of unique k-mers: ${UNIQ_KMER}"

pushd $G15x_HOME

mkdir -p ${G15x_FAST_HOME}/indexes/${CATALOG}
rm -rf ${G15x_FAST_HOME}/indexes/${CATALOG}/${INDEX}_index

apptainer run -B "$G15x_HOME/genbank:/genbank" \
              -B "$G15x_FAST_HOME/indexes:/indexes" \
              "$G15x_HOME/images/kmtricks_latest.sif" \
    pipeline \
        --file /genbank/Human/human_files.fof \
        --run-dir /indexes/${CATALOG}/${INDEX}_index \
        --mode hash:bf:bin \
        --kmer-size $KMER_SIZE \
        -t $N_CPU \
        --hard-min 1 \
        --bloom-size $((UNIQ_KMER * 10)) \
        --nb-partitions $N_PARTITIONS \
        --verbose debug

# apptainer run -B "$G15x_HOME/genbank:/genbank" \
#               -B "$G15x_FAST_HOME/indexes:/indexes" \
#               "$G15x_HOME/images/kmindex_latest.sif" \
#     build \
#         --fof /genbank/Human/human_files.fof \
#         --index /indexes/${CATALOG} \
#         --run-dir /indexes/${CATALOG}/${INDEX}_index \
#         --register-as ${INDEX} \
#         --kmer-size $KMER_SIZE \
#         -t $N_CPU \
#         --hard-min 1 \
#         --bloom-size $((UNIQ_KMER * 10)) \
#         --nb-partitions $N_PARTITIONS \
#         --verbose debug
popd
