#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <stdbool.h>

/*
 * Simple de Bruijn unitig assembler for 31-mers.
 *
 * Input:
 *   - text file, one canonical 31-mer per line (ACGT only)
 * Output:
 *   - FASTA on stdout: unitigs built from the de Bruijn graph
 *     (nodes = 30-mers, edges = 31-mers).
 *
 * Strategy:
 *   - pass 1: count number of kmers (lines) -> N
 *   - pass 2: build node hash, count in/out degrees, count edges (= 2N with revcomp)
 *   - pass 3: allocate adjacency in CSR style and fill edges
 *   - build unitigs from non-branching paths and print FASTA.
 *
 * This code assumes k = 31 and encodes 30-mers in 60 bits of a uint64_t.
 */

#define K 31
#define K1 30

/* ---------- Encoding A/C/G/T as 2 bits ---------- */

static inline uint8_t base_to_bits(char c) {
    switch (c) {
        case 'A': case 'a': return 0;
        case 'C': case 'c': return 1;
        case 'G': case 'g': return 2;
        case 'T': case 't': return 3;
        default:
            fprintf(stderr, "Invalid base: %c\n", c);
            exit(EXIT_FAILURE);
    }
}

static inline char bits_to_base(uint8_t b) {
    b &= 3;
    static const char table[4] = {'A','C','G','T'};
    return table[b];
}

/* Encode a (kmer_len)-mer into low bits of a uint64_t (2 bits/base, MSB = first base) */
static uint64_t encode_kmer(const char *s, int kmer_len) {
    uint64_t v = 0;
    for (int i = 0; i < kmer_len; i++) {
        v = (v << 2) | base_to_bits(s[i]);
    }
    return v;
}

/* Decode a (kmer_len)-mer from low bits of v into out (char*), NUL-terminated */
static void decode_kmer(uint64_t v, int kmer_len, char *out) {
    for (int i = kmer_len - 1; i >= 0; i--) {
        out[i] = bits_to_base((uint8_t)(v & 3));
        v >>= 2;
    }
    out[kmer_len] = '\0';
}

/* Reverse-complement of a kmer (len bases), encoded as uint64_t */
static uint64_t revcomp_encoded(uint64_t v, int kmer_len) {
    uint64_t rc = 0;
    for (int i = 0; i < kmer_len; i++) {
        uint8_t b = (uint8_t)(v & 3);
        v >>= 2;
        /* complement: A<->T (0<->3), C<->G (1<->2) -> 3 - b */
        uint8_t cb = (uint8_t)(3 - b);
        rc = (rc << 2) | cb;
    }
    return rc;
}

/* ---------- Node hash table (open addressing) ---------- */

typedef struct {
    uint64_t key;   /* encoded 30-mer */
    uint32_t value; /* node id */
    uint8_t  used;  /* 0 = empty, 1 = occupied */
} HashEntry;

typedef struct {
    HashEntry *entries;
    size_t capacity;
    size_t size;
} HashTable;

static uint64_t hash_u64(uint64_t x) {
    /* mix bits: splitmix64-like */
    x ^= x >> 33;
    x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33;
    x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= x >> 33;
    return x;
}

static void ht_init(HashTable *ht, size_t capacity) {
    ht->capacity = 1;
    while (ht->capacity < capacity) {
        ht->capacity <<= 1;
    }
    ht->size = 0;
    ht->entries = (HashEntry*)calloc(ht->capacity, sizeof(HashEntry));
    if (!ht->entries) {
        perror("calloc hash");
        exit(EXIT_FAILURE);
    }
}

static void ht_free(HashTable *ht) {
    free(ht->entries);
    ht->entries = NULL;
    ht->capacity = ht->size = 0;
}

/* Insert-or-get: returns node id for key, creating a new one if needed */
static uint32_t ht_get_or_insert(HashTable *ht, uint64_t key, uint32_t *next_id) {
    size_t cap = ht->capacity;
    size_t idx = (size_t)(hash_u64(key) & (cap - 1));
    for (;;) {
        HashEntry *e = &ht->entries[idx];
        if (!e->used) {
            /* new entry */
            e->used  = 1;
            e->key   = key;
            e->value = *next_id;
            ht->size++;
            return (*next_id)++;
        } else if (e->key == key) {
            return e->value;
        }
        idx = (idx + 1) & (cap - 1);
    }
}

/* Lookup only, assuming key exists. If not found, returns UINT32_MAX. */
static uint32_t ht_get(HashTable *ht, uint64_t key) {
    size_t cap = ht->capacity;
    size_t idx = (size_t)(hash_u64(key) & (cap - 1));
    for (;;) {
        HashEntry *e = &ht->entries[idx];
        if (!e->used) {
            return UINT32_MAX;
        }
        if (e->key == key) {
            return e->value;
        }
        idx = (idx + 1) & (cap - 1);
    }
}

/* ---------- Graph structures ---------- */

typedef struct {
    uint64_t code;      /* encoded 30-mer */
    uint32_t in_deg;
    uint32_t out_deg;
    uint32_t out_start; /* index into edges[] */
} Node;

/* edges: adjacency list in CSR form */
typedef struct {
    uint32_t to;
} Edge;

/* ---------- Counting kmers (lines) ---------- */

static uint64_t count_kmers(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) {
        perror("fopen");
        exit(EXIT_FAILURE);
    }
    char *line = NULL;
    size_t len = 0;
    ssize_t r;
    uint64_t n = 0;
    while ((r = getline(&line, &len, f)) != -1) {
        /* skip empty / short lines */
        if (r <= 1) continue;
        /* skip header "kmer" if present */
        if (n == 0 && (strncmp(line, "kmer", 4) == 0)) {
            continue;
        }
        /* crude check: must have at least K chars + newline */
        int bases = 0;
        for (ssize_t i = 0; i < r; i++) {
            if (line[i] == '\n' || line[i] == '\r') break;
            bases++;
        }
        if (bases >= K) {
            n++;
        }
    }
    free(line);
    fclose(f);
    return n;
}

/* ---------- Pass 2: build nodes, degrees, edge count ---------- */

static void build_degrees(
    const char *path,
    HashTable *ht,
    Node **nodes_out,
    uint32_t *n_nodes_out,
    uint64_t *n_edges_out
) {
    uint32_t next_id = 0;
    /* we initialised ht with enough capacity before */

    /* Temporary dynamic array for nodes; we will realloc to final size later */
    uint32_t node_cap = 1024;
    Node *nodes = (Node*)malloc(node_cap * sizeof(Node));
    if (!nodes) {
        perror("malloc nodes");
        exit(EXIT_FAILURE);
    }

    FILE *f = fopen(path, "r");
    if (!f) {
        perror("fopen");
        exit(EXIT_FAILURE);
    }

    char *line = NULL;
    size_t len = 0;
    ssize_t r;

    uint64_t n_edges = 0;

    while ((r = getline(&line, &len, f)) != -1) {
        if (r <= 1) continue;

        /* skip header */
        if (next_id == 0 && strncmp(line, "kmer", 4) == 0) {
            continue;
        }

        /* trim newline */
        char *p = line;
        while (*p && *p != '\n' && *p != '\r') p++;
        *p = '\0';
        int L = (int)strlen(line);
        if (L < K) continue; /* skip malformed */

        /* We treat this as the canonical 31-mer string */
        char *s = line;

        /* Encode kmer and its revcomp */
        uint64_t kmer = encode_kmer(s, K);
        uint64_t kmer_rc = revcomp_encoded(kmer, K);

        /* process both orientations: kmer and kmer_rc */
        for (int ori = 0; ori < 2; ori++) {
            uint64_t kk = (ori == 0) ? kmer : kmer_rc;

            /* prefix and suffix (30-mers) */
            /* prefix: drop last base (2 bits) */
            uint64_t prefix = kk >> 2;
            /* suffix: drop first base; keep low 60 bits */
            uint64_t mask30 = (((uint64_t)1) << (2 * K1)) - 1; /* 60 bits of 1 */
            uint64_t suffix = kk & mask30;

            /* get or create nodes */
            uint32_t id_p = ht_get_or_insert(ht, prefix, &next_id);
            uint32_t id_s = ht_get_or_insert(ht, suffix, &next_id);

            /* ensure nodes array large enough */
            if (id_p >= node_cap || id_s >= node_cap) {
                uint32_t new_cap = node_cap;
                while (id_p >= new_cap || id_s >= new_cap) {
                    new_cap <<= 1;
                }
                Node *tmp = (Node*)realloc(nodes, new_cap * sizeof(Node));
                if (!tmp) {
                    perror("realloc nodes");
                    exit(EXIT_FAILURE);
                }
                /* initialize new range */
                for (uint32_t i = node_cap; i < new_cap; i++) {
                    tmp[i].code = 0;
                    tmp[i].in_deg = tmp[i].out_deg = 0;
                    tmp[i].out_start = 0;
                }
                nodes = tmp;
                node_cap = new_cap;
            }

            /* initialize node code if first time */
            if (nodes[id_p].in_deg == 0 && nodes[id_p].out_deg == 0 && nodes[id_p].code == 0) {
                nodes[id_p].code = prefix;
            }
            if (nodes[id_s].in_deg == 0 && nodes[id_s].out_deg == 0 && nodes[id_s].code == 0) {
                nodes[id_s].code = suffix;
            }

            nodes[id_p].out_deg++;
            nodes[id_s].in_deg++;
            n_edges++;
        }
    }

    free(line);
    fclose(f);

    /* shrink nodes array to actual size = next_id */
    if (next_id < node_cap) {
        Node *tmp = (Node*)realloc(nodes, next_id * sizeof(Node));
        if (!tmp) {
            perror("realloc nodes final");
            exit(EXIT_FAILURE);
        }
        nodes = tmp;
    }

    *nodes_out = nodes;
    *n_nodes_out = next_id;
    *n_edges_out = n_edges;
}

/* ---------- Pass 3: allocate and fill edges ---------- */

static void build_edges(
    const char *path,
    HashTable *ht,
    Node *nodes,
    uint32_t n_nodes,
    Edge **edges_out,
    uint64_t n_edges
) {
    /* compute prefix sums for out_start */
    uint64_t *prefix_sum = (uint64_t*)malloc((n_nodes + 1) * sizeof(uint64_t));
    if (!prefix_sum) {
        perror("malloc prefix_sum");
        exit(EXIT_FAILURE);
    }
    prefix_sum[0] = 0;
    for (uint32_t i = 0; i < n_nodes; i++) {
        prefix_sum[i + 1] = prefix_sum[i] + nodes[i].out_deg;
    }
    if (prefix_sum[n_nodes] != n_edges) {
        fprintf(stderr, "Inconsistent edge count: expected %lu, got %lu\n",
                (unsigned long)n_edges, (unsigned long)prefix_sum[n_nodes]);
        exit(EXIT_FAILURE);
    }

    Edge *edges = (Edge*)malloc(n_edges * sizeof(Edge));
    if (!edges) {
        perror("malloc edges");
        exit(EXIT_FAILURE);
    }

    /* assign out_start */
    for (uint32_t i = 0; i < n_nodes; i++) {
        nodes[i].out_start = (uint32_t)prefix_sum[i]; /* assume n_edges < 2^32, OK here */
    }

    /* temp "cursor" to fill edges per node */
    uint32_t *cursor = (uint32_t*)calloc(n_nodes, sizeof(uint32_t));
    if (!cursor) {
        perror("calloc cursor");
        exit(EXIT_FAILURE);
    }

    FILE *f = fopen(path, "r");
    if (!f) {
        perror("fopen");
        exit(EXIT_FAILURE);
    }

    char *line = NULL;
    size_t len = 0;
    ssize_t r;

    while ((r = getline(&line, &len, f)) != -1) {
        if (r <= 1) continue;

        /* skip header */
        if (strncmp(line, "kmer", 4) == 0) {
            continue;
        }

        char *p = line;
        while (*p && *p != '\n' && *p != '\r') p++;
        *p = '\0';
        int L = (int)strlen(line);
        if (L < K) continue;

        char *s = line;
        uint64_t kmer = encode_kmer(s, K);
        uint64_t kmer_rc = revcomp_encoded(kmer, K);

        uint64_t mask30 = (((uint64_t)1) << (2 * K1)) - 1;

        for (int ori = 0; ori < 2; ori++) {
            uint64_t kk = (ori == 0) ? kmer : kmer_rc;
            uint64_t prefix = kk >> 2;
            uint64_t suffix = kk & mask30;

            uint32_t id_p = ht_get(ht, prefix);
            uint32_t id_s = ht_get(ht, suffix);
            if (id_p == UINT32_MAX || id_s == UINT32_MAX) {
                fprintf(stderr, "Node not found during edge build\n");
                exit(EXIT_FAILURE);
            }

            uint32_t pos = nodes[id_p].out_start + cursor[id_p]++;
            edges[pos].to = id_s;
        }
    }

    free(line);
    fclose(f);
    free(prefix_sum);
    free(cursor);

    *edges_out = edges;
}

/* ---------- Unitig construction ---------- */

static void build_and_print_unitigs(Node *nodes, uint32_t n_nodes, Edge *edges, uint64_t n_edges) {
    (void)n_edges; /* not used directly */

    char node_seq[K1 + 1];

    size_t unitig_cap = 1024;
    char *unitig = (char*)malloc(unitig_cap);
    if (!unitig) {
        perror("malloc unitig");
        exit(EXIT_FAILURE);
    }

    uint64_t unitig_id = 0;

    /* facultatif : marquer les noeuds déjà utilisés comme internes d’une unitig */
    uint8_t *visited = (uint8_t*)calloc(n_nodes, sizeof(uint8_t));
    if (!visited) {
        perror("calloc visited");
        exit(EXIT_FAILURE);
    }

    for (uint32_t u = 0; u < n_nodes; u++) {
        uint32_t indeg = nodes[u].in_deg;
        uint32_t outdeg = nodes[u].out_deg;

        /* pas d’arêtes sortantes -> rien à faire */
        if (outdeg == 0) continue;

        /* nœud interne d’un chemin simple (1-in / 1-out) : pas un start */
        if (indeg == 1 && outdeg == 1) continue;

        /* pour chaque arête sortante de ce nœud de départ */
        uint32_t start_edge = nodes[u].out_start;
        uint32_t end_edge   = start_edge + outdeg;

        for (uint32_t e_idx = start_edge; e_idx < end_edge; e_idx++) {
            uint32_t v = edges[e_idx].to;

            /* initialiser la séquence de l’unitig avec le 30-mer de u */
            decode_kmer(nodes[u].code, K1, node_seq);

            /* taille minimale à prévoir (on ajustera si besoin) */
            size_t needed = K1 + 128;
            if (needed > unitig_cap) {
                unitig_cap = needed * 2;
                unitig = (char*)realloc(unitig, unitig_cap);
                if (!unitig) {
                    perror("realloc unitig");
                    exit(EXIT_FAILURE);
                }
            }

            memcpy(unitig, node_seq, K1);
            size_t len = K1;

            /* ajout de la dernière base du nœud v */
            char last = bits_to_base((uint8_t)(nodes[v].code & 3));
            unitig[len++] = last;

            uint32_t cur = v;

            /* prolonger tant que le nœud courant est 1-in/1-out */
            while (nodes[cur].in_deg == 1 && nodes[cur].out_deg == 1) {
                visited[cur] = 1;

                /* son unique successeur */
                uint32_t e2 = nodes[cur].out_start;
                uint32_t w  = edges[e2].to;

                char last2 = bits_to_base((uint8_t)(nodes[w].code & 3));
                if (len + 1 >= unitig_cap) {
                    unitig_cap *= 2;
                    unitig = (char*)realloc(unitig, unitig_cap);
                    if (!unitig) {
                        perror("realloc unitig 2");
                        exit(EXIT_FAILURE);
                    }
                }
                unitig[len++] = last2;
                cur = w;
            }

            unitig[len] = '\0';

            /* filtrer les unitigs trop courtes (moins d’un k-mer) */
            if (len < K) {
                continue;
            }

            printf(">unitig_%llu\n", (unsigned long long)(++unitig_id));
            printf("%s\n", unitig);
        }
    }

    free(unitig);
    free(visited);
}


/* ---------- Main ---------- */

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s kmers.txt > unitigs.fa\n", argv[0]);
        fprintf(stderr, "kmers.txt: one canonical 31-mer per line (header 'kmer' optional)\n");
        return EXIT_FAILURE;
    }

    const char *kmer_path = argv[1];

    /* Pass 1: count kmers */
    uint64_t n_kmers = count_kmers(kmer_path);
    if (n_kmers == 0) {
        fprintf(stderr, "No kmers found in %s\n", kmer_path);
        return EXIT_FAILURE;
    }
    fprintf(stderr, "[info] kmers: %llu\n", (unsigned long long)n_kmers);

    /* Rough upper bound on number of nodes: 2 * n_kmers (duplication) * 2 ends */
    uint64_t approx_nodes = 4ULL * n_kmers;
    if (approx_nodes < 1024) approx_nodes = 1024;

    /* Init hash table */
    HashTable ht;
    ht_init(&ht, (size_t)(approx_nodes * 2)); /* load factor <= 0.5 */

    /* Pass 2: build nodes + degrees + edge count */
    Node *nodes = NULL;
    uint32_t n_nodes = 0;
    uint64_t n_edges = 0;
    build_degrees(kmer_path, &ht, &nodes, &n_nodes, &n_edges);
    fprintf(stderr, "[info] nodes: %u, edges: %llu\n",
            n_nodes, (unsigned long long)n_edges);

    /* Pass 3: build edges */
    Edge *edges = NULL;
    build_edges(kmer_path, &ht, nodes, n_nodes, &edges, n_edges);

    /* Build / print unitigs */
    build_and_print_unitigs(nodes, n_nodes, edges, n_edges);

    /* Cleanup */
    free(nodes);
    free(edges);
    ht_free(&ht);

    return EXIT_SUCCESS;
}
