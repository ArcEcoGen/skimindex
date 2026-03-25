# Shipping Built-in Commands

In normal use, scripts live in `usercmd/` and never require a rebuild.
The steps below are only needed when you want to **ship a command inside the
container image** itself — for example to distribute it to users who do not
have access to the project directory.

## Adding a built-in subcommand

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

## How the build system works

`docker/build_user_script.sh` assembles `skimindex.sh` from the template
`docker/skimindex.sh.in` by:

- scanning `scripts/` for user-facing scripts (no `_` prefix) and generating
  the sub-command dispatch table (`@@SUBCOMMANDS@@`) and help list
  (`@@SUBCOMMANDS_LIST@@`),
- inlining library files referenced as `# @@INLINE: path@@`,
- substituting `@@KEY@@` placeholders with values supplied via `--set KEY=VALUE`.
