# __skimindex_log.sh

Structured logging through file descriptor 3 (default: stderr; redirected to
the log file when configured).

The active level is set by `[logging].level` in the config (default: `INFO`).
Messages below the active level are silently discarded.

## Functions

| Function | Level | Colour |
|---|---|---|
| `logdebug <msg>` | DEBUG | cyan |
| `loginfo <msg>` | INFO | green |
| `logwarning <msg>` | WARNING | yellow |
| `logerror <msg>` | ERROR | red |

## Example

```bash
loginfo  "Starting download for $SECTION"
logwarning "Output directory already exists — skipping"
logerror "Required variable not set"; exit 1
```
