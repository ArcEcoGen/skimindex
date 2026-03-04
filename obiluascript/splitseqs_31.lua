function worker(sequence)
    local fragment_size = 200
    local overlap = 31 -- chevauchement entre fragments
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
