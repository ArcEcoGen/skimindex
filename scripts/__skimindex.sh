# ============================================================
# __skimindex.sh
# Single entry point for all skimindex bash libraries.
#
# Sources all __skimindex_*.sh libraries in dependency order:
#   1. __skimindex_log.sh      — logging (loginfo, logerror, …)
#   2. __skimindex_config.sh   — TOML config → env vars
#   3. __skimindex_stamping.sh — stamp API (ski_stamp, ski_is_stamped, …)
#
# Each library is guarded against multiple inclusion, so sourcing
# __skimindex.sh more than once (or alongside individual libraries)
# is always safe.
#
# Usage:
#   source /app/scripts/__skimindex.sh
#
# Source this file — do NOT execute it directly.
# ============================================================

# Guard against direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "ERROR: __skimindex.sh is a library — source it, do not run it." >&2
    exit 1
fi

# Resolve this file's own directory (works even when sourced)
_skimindex_sh_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# In dev (outside the container) prefer the .venv python3 and inject its
# site-packages into PYTHONPATH so that all `python3 -m skimindex.*` calls
# work without manual venv activation.
_skimindex_sh_venv="${_skimindex_sh_dir}/../.venv"
if [[ -d "$_skimindex_sh_venv" ]]; then
    # Prepend venv bin so `python3` resolves to the venv interpreter
    export PATH="${_skimindex_sh_venv}/bin:${PATH}"
    _skimindex_sh_site="$(echo "${_skimindex_sh_venv}"/lib/python*/site-packages)"
    [[ -d "$_skimindex_sh_site" ]] && \
        export PYTHONPATH="${_skimindex_sh_site}${PYTHONPATH:+:${PYTHONPATH}}"
fi
unset _skimindex_sh_venv _skimindex_sh_site

source "${_skimindex_sh_dir}/__skimindex_log.sh"
source "${_skimindex_sh_dir}/__skimindex_config.sh"
source "${_skimindex_sh_dir}/__skimindex_stamping.sh"

unset _skimindex_sh_dir
