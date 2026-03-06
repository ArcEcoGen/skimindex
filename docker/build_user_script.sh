#!/usr/bin/env bash
# =============================================================================
# build_user_script.sh — assemble a self-contained user-facing bash script
#
# Usage:
#   build_user_script.sh [options] TEMPLATE
#
# Options:
#   --root DIR           Project root used to resolve @@INLINE: …@@ paths and
#                        to scan for user-facing scripts.
#                        Defaults to the parent of this script's directory.
#   --scripts-dir DIR    Directory to scan for user-facing scripts
#                        (those whose name does not start with __).
#                        Defaults to <root>/scripts.
#   --set KEY=VALUE      Substitute every @@KEY@@ in the output with VALUE.
#                        May be repeated.
#   -h, --help           Print this help and exit.
#
# Template markers:
#   # @@INLINE: relative/path/to/lib.sh@@
#       Replace this line with the content of the referenced file (path
#       relative to --root).  Guard blocks are stripped automatically:
#           # Guard against direct execution
#           if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then … fi
#
#   # @@SUBCOMMANDS_LIST@@
#       Replace with one help line per user-facing script found in
#       --scripts-dir, formatted as:
#           #   <subcommand>   <first description line from script header>
#       plus the built-in subcommands (init, shell).
#
#   # @@SUBCOMMANDS@@
#       Replace with a case block entry per user-facing script:
#           <subcommand>)
#               _ski_run_exec <script>.sh "$@"
#               ;;
#
#   @@KEY@@
#       Substituted with the value supplied via --set KEY=VALUE.
#
# Output goes to stdout; redirect to the target file.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"     # project root = parent of docker/
SCRIPTS_DIR=""                      # resolved below
TEMPLATE="${SCRIPT_DIR}/skimindex.sh.in"   # default template
_template_explicit=0                # set to 1 when given as positional arg
declare -A SUBSTITUTIONS

# Built-in defaults (overridable via --set)
SUBSTITUTIONS["GITHUB_RAW_URL"]="https://raw.githubusercontent.com/ArcEcoGen/skimindex/refs/heads/main"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
            exit 0
            ;;
        --root)        ROOT="$2";        shift 2 ;;
        --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
        --set)
            key="${2%%=*}"; val="${2#*=}"
            SUBSTITUTIONS["$key"]="$val"
            shift 2
            ;;
        --set=*)
            pair="${1#--set=}"; key="${pair%%=*}"; val="${pair#*=}"
            SUBSTITUTIONS["$key"]="$val"
            shift
            ;;
        -*) echo "Error: unknown option '$1'" >&2; exit 1 ;;
        *)
            (( _template_explicit )) && { echo "Error: unexpected argument '$1'" >&2; exit 1; }
            TEMPLATE="$1"; _template_explicit=1; shift
            ;;
    esac
done

[[ -f "$TEMPLATE" ]] || { echo "Error: template not found: $TEMPLATE" >&2; exit 1; }

SCRIPTS_DIR="${SCRIPTS_DIR:-${ROOT}/scripts}"

# Derive FULL_IMAGE from components (unless explicitly overridden via --set)
if [[ -z "${SUBSTITUTIONS[FULL_IMAGE]+x}" ]]; then
    SUBSTITUTIONS["FULL_IMAGE"]="${SUBSTITUTIONS[IMAGE_REGISTRY]}/${SUBSTITUTIONS[IMAGE_NAME]}:${SUBSTITUTIONS[IMAGE_TAG]}"
fi

# ---------------------------------------------------------------------------
# strip_guard <file>
#   Print file content with the direct-execution guard block removed.
#   Guard pattern:
#       # Guard against direct execution
#       if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
#           …
#       fi
# ---------------------------------------------------------------------------
strip_guard() {
    awk '
        /^# Guard against direct execution/      { skip=1; next }
        skip && /^if[[:space:]]*\[\[.*BASH_SOURCE/ { in_if=1; next }
        skip && !in_if                           { skip=0 }
        in_if {
            if (/^fi[[:space:]]*(#.*)?$/) { in_if=0; skip=0 }
            next
        }
        { print }
    ' "$1"
}

# ---------------------------------------------------------------------------
# user_scripts: print sorted list of user-facing script basenames
#   (*.sh in SCRIPTS_DIR, not starting with __, not *.sh.in)
# ---------------------------------------------------------------------------
user_scripts() {
    local f base
    for f in "${SCRIPTS_DIR}"/*.sh; do
        [[ -f "$f" ]] || continue
        base="$(basename "$f")"
        [[ "$base" == _* ]] && continue   # _ prefix: internal; __ prefix: library
        printf '%s\n' "$base"
    done | sort
}

# ---------------------------------------------------------------------------
# script_description <script.sh>
#   Extract a one-line description from the script header.
#   Convention: the first non-empty comment line that is not a separator
#   (====…) and not the bare script filename is taken as the description.
# ---------------------------------------------------------------------------
script_description() {
    local file="${SCRIPTS_DIR}/$1"
    local base="$1"
    awk -v name="$base" '
        NR == 1 { next }          # skip shebang
        /^#[[:space:]]*=+[[:space:]]*$/ { next }   # skip separator lines
        /^#[[:space:]]*$/ { next }                  # skip bare #
        /^[^#]/ { exit }                            # stop at non-comment
        {
            sub(/^#[[:space:]]?/, "")   # strip leading "# "
            if ($0 == name) next        # skip line that is just the filename
            print; exit
        }
    ' "$file" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# generate_subcommands_list
#   Produce the help lines for @@SUBCOMMANDS_LIST@@
# ---------------------------------------------------------------------------
generate_subcommands_list() {
    # Built-in subcommands first
    printf '#   %-24s %s\n' "init" \
        "Initialise a new project directory and download the default config."
    printf '#   %-24s %s\n' "update" \
        "Pull the latest container image from the registry (or refresh the SIF for apptainer)."
    printf '#   %-24s %s\n' "shell" \
        "Start an interactive shell inside the container."

    # Auto-generated from scripts
    local script subcommand desc
    while IFS= read -r script; do
        subcommand="${script%.sh}"
        desc="$(script_description "$script")"
        printf '#   %-24s %s\n' "$subcommand" "$desc"
    done < <(user_scripts)
}

# ---------------------------------------------------------------------------
# generate_subcommands_case
#   Produce the case entries for @@SUBCOMMANDS@@
# ---------------------------------------------------------------------------
generate_subcommands_case() {
    local script subcommand
    while IFS= read -r script; do
        subcommand="${script%.sh}"
        printf '    %s)\n' "$subcommand"
        printf '        _ski_run_exec %s "$@"\n' "$script"
        printf '        ;;\n'
    done < <(user_scripts)
}

# ---------------------------------------------------------------------------
# apply_substitutions <text>
# ---------------------------------------------------------------------------
apply_substitutions() {
    local text="$1"
    local key escaped_val
    for key in "${!SUBSTITUTIONS[@]}"; do
        escaped_val="$(printf '%s\n' "${SUBSTITUTIONS[$key]}" | sed 's|[&/\\]|\\&|g')"
        text="$(printf '%s\n' "$text" | sed "s|@@${key}@@|${escaped_val}|g")"
    done
    printf '%s\n' "$text"
}

# ---------------------------------------------------------------------------
# Main: process the template line by line
# ---------------------------------------------------------------------------
while IFS= read -r line; do

    # @@INLINE: path@@
    if [[ "$line" =~ ^[[:space:]]*#[[:space:]]*@@INLINE:[[:space:]]*([^@]+)@@[[:space:]]*$ ]]; then
        rel="${BASH_REMATCH[1]}"
        rel="${rel#"${rel%%[![:space:]]*}"}"; rel="${rel%"${rel##*[![:space:]]}"}"
        target="${ROOT}/${rel}"
        [[ -f "$target" ]] || { echo "Error: @@INLINE: $rel@@ — not found: $target" >&2; exit 1; }
        apply_substitutions "$(strip_guard "$target")"

    # @@SUBCOMMANDS_LIST@@
    elif [[ "$line" =~ ^[[:space:]]*#[[:space:]]*@@SUBCOMMANDS_LIST@@[[:space:]]*$ ]]; then
        generate_subcommands_list

    # @@SUBCOMMANDS@@
    elif [[ "$line" =~ ^[[:space:]]*#[[:space:]]*@@SUBCOMMANDS@@[[:space:]]*$ ]]; then
        generate_subcommands_case

    else
        apply_substitutions "$line"
    fi

done < "$TEMPLATE"
