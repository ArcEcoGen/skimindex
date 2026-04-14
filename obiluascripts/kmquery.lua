-- ============================================================
-- kmquery.lua
-- OBITools4 obiscript — query kmindex-server for each sequence.
--
-- Each input sequence is sent to kmindex-server and the response
-- is attached as an annotation to the sequence.
--
-- Configuration (environment variables):
--   KMINDEX_SERVER    Path to kmindex-server binary.
--                     Default: kmindex-server
--   KMINDEX_HOST      Server host.
--                     Default: 127.0.0.1
--   KMINDEX_PORT      Server port.
--                     Default: 8080
--   KMINDEX_Z         Z parameter for kmindex.
--                     Default: 3
--   KMINDEX_R         R parameter for kmindex.
--                     Default: 0.0
--   KMINDEX_CONTAM_NOT_OK_LIBS  Libraries that indicate contamination.
--                     Default: Human,Fungi,Bacteria
--   KMINDEX_CONTAM_OK_LIBS      Libraries that are NOT contamination (override).
--                     Default: (none)
--   KMINDEX_LIBRARIES Explicit libraries list (optional, overrides auto-union).
--   KMINDEX_THREADS      Max threads for kmindex-server.
--                        Default: nproc×2
--   KMINDEX_CONCURRENCY    Max simultaneous HTTP requests from obiscript.
--                          Default: nproc
--   KMINDEX_RETRY_MAX      Max retry attempts on HTTP error.
--                          Default: 3
--   KMINDEX_RETRY_DELAY_MS Initial retry delay in ms (doubles each attempt).
--                          Default: 500
--   KMINDEX_TIMEOUT_MS     HTTP request timeout in ms.
--                          Default: 300000
--   KMINDEX_MANAGE_SERVER  Set to "false" to skip server start/stop.
--                     Default: server is managed by the script
--
-- Output annotations:
--   kmindex_library   Name of the matched library (or "none")
--   kmindex_score     Match score
--   contamination     true if matched in NOT_OK and not in OK; false otherwise
--
-- Usage:
--   obiscript -S /app/obiluascripts/kmquery.lua <input.fasta.gz>
--
--   KMINDEX_CONTAM_NOT_OK_LIBS="Human,Fungi,Bacteria" \
--   KMINDEX_CONTAM_OK_LIBS="Plants" \
--   obiscript -S /app/obiluascripts/kmquery.lua <input.fasta.gz>
--
--   KMINDEX_LIBRARIES="Human,Fungi,Bacteria,Plants" \
--   obiscript -S /app/obiluascripts/kmquery.lua <input.fasta.gz>
-- ============================================================

-- json is a global provided by OBITools4 (native Go module, no require needed)

local DEBUG       = os.getenv("KMINDEX_DEBUG") ~= nil

local SERVER_PATH = os.getenv("KMINDEX_SERVER") or "kmindex-server"
local SERVER_HOST = os.getenv("KMINDEX_HOST") or "127.0.0.1"
local SERVER_PORT = tonumber(os.getenv("KMINDEX_PORT")) or 8080
local KMINDEX_Z   = tonumber(os.getenv("KMINDEX_Z")) or 3
local KMINDEX_R   = tonumber(os.getenv("KMINDEX_R")) or 0.0

local URL         = string.format("http://%s:%d/kmindex/query", SERVER_HOST, SERVER_PORT)

local function split_csv(str)
    local result = {}
    for v in str:gmatch("[^,]+") do
        table.insert(result, (v:gsub("^%s+", ""):gsub("%s+$", "")))
    end
    return result
end

local NOT_OK_STR         = os.getenv("KMINDEX_CONTAM_NOT_OK_LIBS") or "Human,Fungi,Bacteria"
local OK_STR             = os.getenv("KMINDEX_CONTAM_OK_LIBS") or ""

local CONTAM_NOT_OK_LIBS = {}
for _, lib in ipairs(split_csv(NOT_OK_STR)) do
    CONTAM_NOT_OK_LIBS[lib] = true
end

local CONTAM_OK_LIBS = {}
for _, lib in ipairs(split_csv(OK_STR)) do
    CONTAM_OK_LIBS[lib] = true
end

local explicit_libs = os.getenv("KMINDEX_LIBRARIES")
local LIBRARIES
if explicit_libs then
    LIBRARIES = split_csv(explicit_libs)
elseif OK_STR ~= "" then
    LIBRARIES = split_csv(NOT_OK_STR .. "," .. OK_STR)
else
    LIBRARIES = split_csv(NOT_OK_STR)
end

local function start_server()
    local index_dir = os.getenv("KMINDEX_INDEX_DIR") or "/indexes/decontamination"
    local log_dir   = os.getenv("KMINDEX_LOG_DIR") or "/log"
    local _h        = io.popen("nproc")
    local _nproc    = (_h:read("*n") or 1) * 2
    _h:close()
    local threads = tonumber(os.getenv("KMINDEX_THREADS")) or _nproc
    local cmd     = string.format(
        "%s -i %s -d %s --threads %s > /dev/null 2>&1 &",
        SERVER_PATH, index_dir, log_dir, threads
    )
    os.execute(cmd)

    -- Poll until the server responds (max 30s, 500ms timeout per probe)
    local probe = json.encode({ index = LIBRARIES, id = { "probe" }, seq = { "A" }, z = 0, format = "json", r = 0.0 })
    for _ = 1, 300 do
        local resp, err = http.post(URL, probe, 500)
        if resp and not err then
            return
        end
        os.execute("sleep 0.1")
    end
    error("kmindex-server did not become ready within 30 seconds")
end

local function stop_server()
    os.execute("pkill -f 'kmindex-server'")
end

local RETRY_MAX    = tonumber(os.getenv("KMINDEX_RETRY_MAX")) or 3
local RETRY_DELAY  = tonumber(os.getenv("KMINDEX_RETRY_DELAY_MS")) or 500
local HTTP_TIMEOUT = tonumber(os.getenv("KMINDEX_TIMEOUT_MS")) or 300000

-- Query kmindex-server with a batch of sequences.
-- ids and seqs are arrays of the same length.
-- Retries up to RETRY_MAX times with exponential backoff on error.
-- Returns the raw JSON response string, or nil if all retries fail.
local function query_server(ids, seqs)
    local payload = json.encode({
        index  = LIBRARIES,
        id     = ids,
        seq    = seqs,
        z      = KMINDEX_Z,
        format = "json",
        r      = KMINDEX_R,
    })
    if DEBUG then
        local started   = obicontext.inc("req_started")
        local in_flight = started - obicontext.item("req_done")
        io.stderr:write(string.format(
            "[kmquery] batch=%d  req_in_flight=%d\n", #ids, in_flight))
    end

    local response, err
    local delay = RETRY_DELAY
    for attempt = 1, RETRY_MAX + 1 do
        response, err = http.post(URL, payload, HTTP_TIMEOUT)
        if response and not err then
            if DEBUG then obicontext.inc("req_done") end
            return response
        end
        obicontext.inc("req_errors")
        if attempt <= RETRY_MAX then
            io.stderr:write(string.format(
                "[kmquery] attempt %d/%d failed: %s — retrying in %dms\n",
                attempt, RETRY_MAX + 1, err, delay))
            os.execute(string.format("sleep %.3f", delay / 1000.0))
            delay = delay * 2 -- exponential backoff
        else
            io.stderr:write(string.format(
                "[kmquery] all %d attempts failed for batch of %d sequences: %s\n",
                RETRY_MAX + 1, #ids, err))
        end
    end
    if DEBUG then obicontext.inc("req_done") end
    return nil, err
end

-- Annotate a single sequence from the decoded response data.
-- data is the full json.decode() result (keyed by library → seq_id → hits).
local function annotate(sequence, seq_id, data)
    local matched_libs = {}
    local best_lib     = nil
    local best_score   = 0

    if data then
        for _, lib in ipairs(LIBRARIES) do
            local lib_data = data[lib]
            if lib_data then
                local hits = lib_data[seq_id]
                if type(hits) == "table" then
                    for _, score in pairs(hits) do
                        if type(score) == "number" and score > 0 then
                            matched_libs[lib] = true
                            if score > best_score then
                                best_score = score
                                best_lib   = lib
                            end
                        end
                    end
                end
            end
        end
    end

    local in_not_ok, in_ok = false, false
    local all_matched, not_ok_matched = {}, {}
    for lib in pairs(matched_libs) do
        table.insert(all_matched, lib)
        if CONTAM_NOT_OK_LIBS[lib] then
            in_not_ok = true; table.insert(not_ok_matched, lib)
        end
        if CONTAM_OK_LIBS[lib] then in_ok = true end
    end
    table.sort(all_matched)
    table.sort(not_ok_matched)

    local contamination = in_not_ok and not in_ok

    sequence:attribute("kmindex_score", best_score)
    sequence:attribute("contamination", contamination)
    sequence:attribute("kmindex_contam_libraries", not_ok_matched)
    sequence:attribute("kmindex_matched_libraries", all_matched)
    sequence:attribute("kmindex_best_match", best_lib)


    if DEBUG then
        io.stderr:write(string.format(
            "[kmquery] %s  contam=%s  score=%.4f  contam_libs=[%s]  matched=[%s]\n",
            seq_id, tostring(contamination), best_score,
            table.concat(not_ok_matched, ","), table.concat(all_matched, ",")
        ))
    end
end

function begin()
    obicontext.item("req_started", 0)
    obicontext.item("req_done", 0)
    obicontext.item("req_errors", 0)
    local manage_server = os.getenv("KMINDEX_MANAGE_SERVER")
    if manage_server ~= "false" then
        obicontext.item("manage_server", true)
        start_server()
    else
        obicontext.item("manage_server", false)
    end
    -- Limit concurrent HTTP requests to avoid overwhelming kmindex-server.
    -- Default: same value as --threads (nproc×2); override with KMINDEX_CONCURRENCY.
    local _h     = io.popen("nproc")
    local _nproc = (_h:read("*n") or 1)
    _h:close()
    local concurrency = tonumber(os.getenv("KMINDEX_CONCURRENCY")) or _nproc
    http.set_concurrency(concurrency)
end

function slice_worker(slice)
    local n    = slice:len()
    local ids  = {}
    local seqs = {}
    for i = 0, n - 1 do
        local s     = slice:sequence(i)
        ids[i + 1]  = s:id()
        seqs[i + 1] = s:sequence()
    end

    local response, query_err = query_server(ids, seqs)

    if not response then
        for i = 0, n - 1 do
            slice:sequence(i):attribute("kmindex_error", query_err or "unknown error")
        end
    else
        local data = json.decode(response)
        for i = 0, n - 1 do
            local s = slice:sequence(i)
            annotate(s, ids[i + 1], data)
        end
    end

    return slice
end

function finish()
    local errors = obicontext.item("req_errors")
    if errors > 0 then
        io.stderr:write(string.format(
            "[kmquery] WARNING: %d HTTP request attempts failed (after retries)\n", errors))
    end
    if obicontext.item("manage_server") then
        stop_server()
    end
end
