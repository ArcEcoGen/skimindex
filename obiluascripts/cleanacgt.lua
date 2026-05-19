-- ============================================================
-- cleanacgt.lua
-- OBITools4 obiscript — split sequences into [ACGTacgt]+ segments.
--
-- Non-ACGT characters (N, IUPAC ambiguity codes, gaps, …) act as
-- split points.  Each contiguous run of pure ACGT bases is emitted
-- as a separate output sequence.  The position within the parent
-- sequence is preserved via subsequence(), so quality scores and
-- annotations are carried over when available.
--
-- Usage:
--   obiscript -S /app/obiluascripts/cleanacgt.lua <input.fasta.gz>
-- ============================================================

function worker(sequence)
    local seq_str = sequence:sequence()
    local slice   = BioSequenceSlice.new()
    local pos     = 1

    while pos <= #seq_str do
        local s, e = seq_str:find("[ACGTacgt]+", pos)
        if not s then break end
        -- subsequence() is 0-based, end exclusive
        local sub = sequence:subsequence(s - 1, e)
        slice:push(sub)
        pos = e + 1
    end

    return slice
end
