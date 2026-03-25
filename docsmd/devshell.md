# Writing Shell Commands

Shell commands are bash scripts placed in the project's `usercmd/` directory.
They become available as `skimindex <name>` subcommands **without rebuilding
the container image**.

---

## Quick start

**Step 1.** Create `usercmd/` in your project root (done automatically by `skimindex init`):

```bash
mkdir -p usercmd
```

**Step 2.** Write a script there, e.g. `usercmd/hello.sh`:

```bash
#!/usr/bin/env bash
# ============================================================
# hello.sh
# Say hello — one-line description shown in skimindex --help.
# ============================================================
set -euo pipefail

source "${SKIMINDEX_SCRIPTS_DIR}/__skimindex.sh"   # logging + config + stamping

loginfo "Hello, skimindex!"
```

**Step 3.** Invoke it immediately — no rebuild needed:

```bash
skimindex hello
```

The first non-empty, non-separator comment line after the filename becomes the
description shown in `skimindex --help` under the *user subcommands* section.

### How it works

`usercmd/` is declared in `config/skimindex.toml`:

```toml
[local_directories]
usercmd = "usercmd"   # bind-mounted to /usercmd inside the container
```

When a subcommand is not built-in, `skimindex.sh` checks for
`/usercmd/<subcmd>.sh` and executes it with `bash`.  Before calling the script
it exports `SKIMINDEX_SCRIPTS_DIR=/app/scripts` so that `__skimindex.sh` can
always be sourced portably.

---

## Adding options

Use a standard `while` / `case` loop.  Expose `--help` by re-printing the
header block with `sed`:

```bash
#!/usr/bin/env bash
# ============================================================
# greet.sh
# Print a greeting for a given name.
#
# Usage:
#   skimindex greet --name NAME [--shout]
# ============================================================

set -euo pipefail

source "${SKIMINDEX_SCRIPTS_DIR}/__skimindex.sh"

NAME=""
SHOUT=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            sed -En '2,/^# =+$/{ s/^# ?//; /^=+$/d; p; }' "$0"
            exit 0
            ;;
        --name)   NAME="$2";  shift 2 ;;
        --shout)  SHOUT=true; shift   ;;
        *) logerror "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$NAME" ]] && { logerror "--name is required"; exit 1; }

msg="Hello, ${NAME}!"
[[ "$SHOUT" == true ]] && msg="${msg^^}"
loginfo "$msg"
```

---

## Using configuration variables

After `source __skimindex.sh`, all `[data.X]`, `[role.X]`, `[source.X]` and
root-level values from `config/skimindex.toml` are available as environment
variables.

```bash
#!/usr/bin/env bash
# ============================================================
# show_config.sh
# Display resolved paths for a data section.
#
# Usage:
#   skimindex show_config --section NAME
# ============================================================

set -euo pipefail

source "${SKIMINDEX_SCRIPTS_DIR}/__skimindex.sh"

SECTION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --section) SECTION="$2"; shift 2 ;;
        *) logerror "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$SECTION" ]] && { logerror "--section is required"; exit 1; }

SECTION_UP="${SECTION^^}"

source_var="SKIMINDEX__DATA__${SECTION_UP}__SOURCE"
role_var="SKIMINDEX__DATA__${SECTION_UP}__ROLE"
dir_var="SKIMINDEX__DATA__${SECTION_UP}__DIRECTORY"

loginfo "Section  : $SECTION"
loginfo "Source   : ${!source_var:-<not set>}"
loginfo "Role     : ${!role_var:-<not set>}"
loginfo "Directory: ${!dir_var:-<not set>}"
```

The full list of sections and their variables is produced at runtime by
`python3 -m skimindex.config` (the same call made by `__skimindex_config.sh`).

---

See [Bash Shell API Reference](api/shell_index.md) for logging, stamp, and
configuration variable references.
