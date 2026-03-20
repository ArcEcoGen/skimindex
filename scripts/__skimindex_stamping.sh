# ============================================================
# __skimindex_stamping.sh
# Loads bash wrappers for all skimindex stamp functions.
#
# Each wrapper calls the Python implementation via:
#   python3 -m skimindex.stamp <fn_name> [args...]
#
# Boolean return values map to POSIX exit codes (True → 0, False → 1),
# so wrappers can be used directly in if statements:
#
#   if ski_is_stamped "$output_dir"; then
#       echo "already done"
#   fi
#
#   ski_stamp "$output_dir"
#   ski_needs_run "$path" "$src1" "$src2" --dry-run --label "human"
#
# Source this file — do NOT execute it directly.
# ============================================================

# Guard against direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: __skimindex_stamping.sh is a library — source it, do not run it." >&2
    exit 1
fi

# Guard against multiple inclusion
[[ -n "${_SKIMINDEX_STAMPING_LOADED:-}" ]] && return 0

# Require __skimindex.sh as entry point (_skimindex_sh_dir must be set)
if [[ -z "${_skimindex_sh_dir:-}" ]]; then
    echo "ERROR: source __skimindex.sh instead of __skimindex_stamping.sh directly." >&2
    return 1
fi

_SKIMINDEX_STAMPING_LOADED=1

# Generate and load the bash wrappers from the Python module
if ! _ski_stamp_wrappers="$(python3 -m skimindex.stamp 2>&1)"; then
    echo "ERROR: __skimindex_stamping.sh: failed to generate stamp wrappers" >&2
    echo "$_ski_stamp_wrappers" >&2
else
    eval "$_ski_stamp_wrappers"
fi

unset _ski_stamp_wrappers
