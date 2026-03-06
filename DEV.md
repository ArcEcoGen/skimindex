# G15x project 

## The G15x conda environment

All the programs will be part of the `G15x` conda environment.
To activate conda on Gricad

```bash
. /applis/environments/conda.sh
```

you can also add an alias in your `~/.bashrc` file

```bash
alias condaenv='. /applis/environments/conda.sh'
```

### Activating the conda environment

```bash
conda activate G15x
```

to share the environment you need to 

```bash
conda env export --name G15x --file /bettik/LECA/home/pan/G15X/share/G15x_conda.yml && chmod g+w /bettik/LECA/home/pan/G15X/share/G15x_conda.yml 
```

```bash
conda env update --name G15x --file /bettik/LECA/home/pan/G15X/share/G15x_conda.yml --prune
```


## Structure of the directory

```
G15X/
├── bin : all the scripts and binaries
├── etc : global configuration for the G15x environment
├── genbank : data downloaded from Genbank for decontamination purposes
│   ├── Fungi : the Fugi sequences extracted from PLN Genbank division
│   ├── Human : The human reference genome
│   ├── Plants : a set of 99 complete plant genome from Genbank
│   │   └── plant_genomes_gbff
│   ├── Release_269.0 : the bacterial (bct) and plant/fungi (pln) genbank divisions
│   │   ├── fasta
│   │   │   ├── bct
│   │   │   └── pln
│   └── scripts : set of bash script for managing decontamination of the genomes 
├── images : the dockers images in SIF format to use with apptainer
├── indexes : the directory containing the kmtricks indexes
│   └── decontamination
├── ncbi : supplementary plant genome of interest downloaded from NCBI
│   └── species
├── processed : processed plant genomes
│   └── species
├── rawdata : raw sequence genome produced at Tromsoe or Edinburgh 
│   ├── hybrid
│   ├── species
│   └── undetermine
├── share : to EC -> to be moved into etc
└── src : sources for small binaries
    └── kmerasm : computes unitig from a set of kmers
```

## Preparing decontamination index

### Counting kmers into the human/plants/fungi data

- for the human genome (`/bettik/LECA/home/pan/G15X/genbank/Human`)

```bash
ntcard -k 31 \
       -o human_kmer_spectrum.txt \
       human_genome.fasta.gz \
       2>&1 \
| head -2 \
> human_kmer_stats.txt
```

- for the plant genomes (`/bettik/LECA/home/pan/G15X/genbank/Plants`)

```bash
ntcard -k 31 \
       -o plants_kmer_spectrum.txt \
       plant_genomes.fasta.gz \
       2>&1 \
| head -2 \
> plants_kmer_stats.txt
```

- for the fungi (`/bettik/LECA/home/pan/G15X/genbank/Fungi`)

```bash
ntcard -k 31 \
       -o fungi_kmer_spectrum.txt \
       all_fungi.fasta.gz \
       2>&1 \
| head -2 \
> fungi_kmer_stats.txt
```

- for the bacteria (`/bettik/LECA/home/pan/G15X/genbank/Release_269.0/fasta`)

```bash
ntcard -k 31 \
       -o bct_kmer_spectrum.txt \
       -t 30 \
       bct/*.fasta.gz \
       2>&1 \
| head -2 \
> bct_kmer_stats.txt
```

- for the bacteria (`/bettik/LECA/home/pan/G15X/genbank/`)

```bash
ntcard -k 31 \
       -o bct_kmer_spectrum.txt \
       -t 15 \
       bct/*.fasta.gz \
       2>&1 \
| head -2 \
> bct_kmer_stats.txt
```

### Indexing the decontamination index

#### Splitting sequences into fragments

The idea is to split sequences into fragments of size 200 with an overlap of kmer size to facilitate k-mer indexing.

```
 |----------------------------------------------------------------->
  |---->
      |---->
          |---->
```

Two possible commands are:

```bash
seqkit sliding --step 169 \
               --window 200 \
               all_fungi.fasta.gz \
| gzip -9c > fragmentfungi.fasta.gz
```

##### An example for human genome with obitools

The chromosomes are split into 200 bp fragments, overlapping by kmers of size 31.
The resulting fragments are filtered to remove sequences with only Ns.
And lastly, the fragments are distributed across 20 different files.

```bash
G15x_HOME=/bettik/LECA/home/pan/G15X
mkdir -p $G15x_HOME/genbank/Human/fragments
obiscript -S $G15x_HOME/bin/splitseqs_31.lua \
          $G15x_HOME/genbank/Human/human_genome.fasta.gz \
| obigrep -v -s '^n+$' \
| obidistribute -Z -n 20 \
               -p $G15x_HOME/genbank/Human/fragments/human_genome_frg_%s.fasta.gz
```

#### Indexing genome files with kmtricks

Produce human files fof including the 20 fragment files to be used by kmtricks

```bash
G15x_HOME=/bettik/LECA/home/pan/G15X
pushd $G15x_HOME
ls -1 genbank/Human/fragments/* \
| awk 'BEGIN {ORS=" "; print "human:"} 
             {print "/"$1" ;"} 
         END {print "\n"}' \
| sed 's/ ; *$//' > $G15x_HOME/genbank/Human/human_files.fof
popd
```

Run kmtricks on human files to produce a kmtricks index including the 29-mers.
The idea is to look at three 29-mers instead of one 31-mer to reduce the number of false positives.

```bash
INDEX="human"
KMER_SIZE=29
N_CPU=10
G15x_HOME=/bettik/LECA/home/pan/G15X
G15x_FAST_HOME=/silenus/PROJECTS/pr-phyloalps/coissac/G15x
UNIQ_KMER=$(awk '(NR==2) {print $NF}' $G15x_HOME/genbank/Human/human_kmer_stats.txt)
pushd $G15x_HOME
mkdir -p ${G15x_FAST_HOME}/indexes/decontamination
rm -rf ${G15x_FAST_HOME}/indexes/decontamination/${INDEX}_index
apptainer run -B "$G15x_HOME/genbank:/genbank" \
              -B "$G15x_FAST_HOME/indexes:/indexes" \
              "$G15x_HOME/images/kmtricks_latest.sif" \
    pipeline \
        --file /genbank/Human/human_files.fof \
        --run-dir /indexes/decontamination/${INDEX}_index \
        --mode hash:bf:bin \
        --kmer-size $KMER_SIZE \
        -t 5 \
        --hard-min 1 \
        --bloom-size $((UNIQ_KMER * 10)) \
        --nb-partitions 10 \
        --verbose debug
popd
```

/silenus/PROJECTS/pr-phyloalps/coissac

apptainer shell "$G15x_HOME/images/kmtricks_latest.sif"
