function begin()
    local fragment_size = tonumber(os.getenv("FRAGMENT_SIZE")) or 200
    local overlap       = tonumber(os.getenv("OVERLAP"))       or 28
    obicontext.item("fragment_size", fragment_size)
    obicontext.item("overlap",       overlap)
end

function worker(sequence)
    local fragment_size = obicontext.item("fragment_size")
    local overlap         = obicontext.item("overlap")
    local sequence_length = sequence:len()

    local slice = BioSequenceSlice.new()

    local i = 0 -- index de départ (0-based)
    while i < sequence_length do
        local end_pos = i + fragment_size
        if end_pos > sequence_length then
            end_pos = sequence_length
        end
        local fragment = sequence:subsequence(i, end_pos) -- end exclus
        slice:push(fragment)

        -- avancer de fragment_size - overlap
        i = i + (fragment_size - overlap)
    end

    return slice
end
