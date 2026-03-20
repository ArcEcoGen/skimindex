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
variables.  See [Environment Variables](environment-variables.md) for the full
naming convention.

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

## Logging functions

`__skimindex_log.sh` provides structured logging through file descriptor 3
(default: stderr; redirected to the log file when configured).

| Function | Level | Colour |
|---|---|---|
| `logdebug <msg>` | DEBUG | cyan |
| `loginfo <msg>` | INFO | green |
| `logwarning <msg>` | WARNING | yellow |
| `logerror <msg>` | ERROR | red |

The active level is set by `[logging].level` in the config (default: `INFO`).
Messages below the active level are silently discarded.

```bash
loginfo  "Starting download for $SECTION"
logwarning "Output directory already exists — skipping"
logerror "Required variable not set"; exit 1
```

---

## Stamp functions

`__skimindex_stamping.sh` exposes the Python stamp API as shell functions
(prefixed `ski_`).  They map boolean returns to POSIX exit codes
(True → 0, False → 1), so they work directly in `if` statements.

| Function | Description |
|---|---|
| `ski_stamp <path>` | Mark *path* as successfully completed |
| `ski_is_stamped <path>` | Return 0 if *path* has a stamp |
| `ski_unstamp <path>` | Remove the stamp (force re-run) |
| `ski_remove_if_not_stamped <path>` | Delete *path* if it has no stamp |
| `ski_needs_run <path> [sources…] [--dry-run] [--label L] [--action A]` | Three-way branch: already done / dry-run / must run |
| `ski_newer_than_stamp <path> <stamped>` | Return 0 if *path* is newer than the stamp of *stamped* |
| `ski_unstamp_if_newer <path> [sources…]` | Invalidate stamp when a dependency changes |
| `ski_stamp_gz <path>` | Verify gzip integrity then stamp |

Pass `--help` to any function to see the full argument reference:

```bash
ski_needs_run --help
```

Typical pattern for an idempotent step:

```bash
OUTPUT_DIR="/processed_data/Human/split"

if ski_needs_run "$OUTPUT_DIR" "$INPUT_FILE" \
        --label "human:split" --action "split sequences"; then
    ski_remove_if_not_stamped "$OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"

    # … do the work …

    ski_stamp "$OUTPUT_DIR"
fi
```

---

# Advanced development 

## shipping a command inside the image

In normal use, scripts live in `usercmd/` and never require a rebuild.
The steps below are only needed when you want to **ship a command inside the
container image** itself — for example to distribute it to users who do not
have access to the project directory.

### Adding a built-in subcommand

**Step 1.** Place the script in `scripts/` (no `_` prefix).  Use `$SCRIPT_DIR` to
locate the library instead of `SKIMINDEX_SCRIPTS_DIR`:

```bash
#!/usr/bin/env bash
# ============================================================
# hello.sh
# Say hello — built-in version.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/__skimindex.sh"

loginfo "Hello from inside the image!"
```

**Step 2.** Rebuild the image **and** regenerate `skimindex.sh`:

```bash
make -C docker
```

The script now appears as a built-in in `skimindex --help` and is available
even without a `usercmd/` directory.

### How the build system works

`docker/build_user_script.sh` assembles `skimindex.sh` from the template
`docker/skimindex.sh.in` by:

- scanning `scripts/` for user-facing scripts (no `_` prefix) and generating
  the sub-command dispatch table (`@@SUBCOMMANDS@@`) and help list
  (`@@SUBCOMMANDS_LIST@@`),
- inlining library files referenced as `# @@INLINE: path@@`,
- substituting `@@KEY@@` placeholders with values supplied via `--set KEY=VALUE`.
