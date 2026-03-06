-- ============================================================
-- splitseqs_31.lua
-- OBITools4 obiscript — split sequences into overlapping fragments.
--
-- Each input sequence is cut into fixed-size windows that overlap
-- so that every k-mer spanning a boundary is captured in at least
-- one fragment, making the tiling suitable for k-mer index building.
--
-- Configuration (environment variables):
--   FRAGMENT_SIZE   Length of each fragment in base pairs.
--                   Default: 200
--   OVERLAP         Number of bases shared between consecutive
--                   fragments.  Should be set to (kmer_size - 1)
--                   so that every k-mer spanning a boundary is
--                   represented in at least one fragment.
--                   Default: 28  (suitable for kmer_size = 29)
--
-- Usage:
--   FRAGMENT_SIZE=200 OVERLAP=28 \
--   obiscript -S /app/obiluascripts/splitseqs_31.lua <input.fasta.gz>
--
-- Typically called from split_references.sh, which sets these
-- variables automatically from the [decontamination] section of
-- config/skimindex.toml.
-- ============================================================

function begin()
    local fragment_size = tonumber(os.getenv("FRAGMENT_SIZE")) or 200
    local overlap       = tonumber(os.getenv("OVERLAP"))       or 28
    obicontext.item("fragment_size", fragment_size)
    obicontext.item("overlap",       overlap)
end

function worker(sequence)
    local fragment_size   = obicontext.item("fragment_size")
    local overlap         = obicontext.item("overlap")
    local sequence_length = sequence:len()

    local slice = BioSequenceSlice.new()

    local i = 0 -- 0-based start position
    while i < sequence_length do
        local end_pos = i + fragment_size
        if end_pos > sequence_length then
            end_pos = sequence_length
        end
        local fragment = sequence:subsequence(i, end_pos) -- end exclusive
        slice:push(fragment)

        i = i + (fragment_size - overlap)
    end

    return slice
end
