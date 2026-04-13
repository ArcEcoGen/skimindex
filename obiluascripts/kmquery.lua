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
--   KMINDEX_THREADS   Max parallel connections for kmindex-server.
--                     Default: nproc
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

local json        = require("dkjson")

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
    local _nproc    = (io.popen("nproc"):read("*n") or 1) * 2
    local threads   = tonumber(os.getenv("KMINDEX_THREADS")) or _nproc
    local cmd       = string.format(
        "%s -i %s -d %s --threads %s > /dev/null 2>&1 &",
        SERVER_PATH, index_dir, log_dir, threads
    )
    os.execute(cmd)

    -- Poll until the server responds (max 30s)
    local probe = json.encode({ index = LIBRARIES, id = "probe", seq = { "A" }, z = 0, format = "json", r = 0.0 })
    for _ = 1, 300 do
        local resp, err = http.post(URL, probe)
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

local function query_server(seq_id, sequence)
    local payload = json.encode({
        index  = LIBRARIES,
        id     = seq_id,
        seq    = { sequence },
        z      = KMINDEX_Z,
        format = "json",
        r      = KMINDEX_R,
    })
    local response, err = http.post(URL, payload)
    if err then
        return nil
    end
    return response
end

-- Returns:
--   matched_libs      set of all libraries with at least one hit
--   best_not_ok_lib   NOT_OK library with the highest score (nil if none)
--   best_not_ok_score max score across NOT_OK libraries (0 if none)
local function parse_response(response)
    if not response then
        return {}, nil, 0
    end
    local data = json.decode(response)
    if not data then
        return {}, nil, 0
    end

    local matched_libs      = {}
    local best_not_ok_lib   = nil
    local best_not_ok_score = 0

    for _, lib in ipairs(LIBRARIES) do
        local lib_data = data[lib]
        if lib_data then
            for _, hits in pairs(lib_data) do
                if type(hits) == "table" then
                    for _, score in pairs(hits) do
                        if type(score) == "number" and score > 0 then
                            matched_libs[lib] = true
                            if CONTAM_NOT_OK_LIBS[lib] and score > best_not_ok_score then
                                best_not_ok_score = score
                                best_not_ok_lib   = lib
                            end
                        end
                    end
                end
            end
        end
    end

    return matched_libs, best_not_ok_lib, best_not_ok_score
end

function begin()
    local manage_server = os.getenv("KMINDEX_MANAGE_SERVER")
    if manage_server ~= "false" then
        obicontext.item("manage_server", true)
        start_server()
    else
        obicontext.item("manage_server", false)
    end
end

function worker(sequence)
    local seq_id                               = sequence:id()
    local seq                                  = sequence:sequence()

    local response                             = query_server(seq_id, seq)
    local matched_libs, best_lib, not_ok_score = parse_response(response)

    local in_not_ok                            = false
    local in_ok                                = false
    local all_matched, not_ok_matched          = {}, {}
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

    sequence:attribute("kmindex_score",            not_ok_score)
    sequence:attribute("contamination",            contamination)
    sequence:attribute("kmindex_contam_libraries", not_ok_matched)
    sequence:attribute("kmindex_matched_libraries", all_matched)
    if contamination then
        sequence:attribute("kmindex_best_match",   best_lib)
    end

    if DEBUG then
        io.stderr:write(string.format(
            "[kmquery] %s  contam=%s  score=%.4f  contam_libs=[%s]  matched=[%s]\n%s\n",
            seq_id, tostring(contamination), not_ok_score,
            table.concat(not_ok_matched, ","), table.concat(all_matched, ","),
            sequence:string("obi")
        ))
    end
    return sequence
end

function finish()
    if obicontext.item("manage_server") then
        stop_server()
    end
end
