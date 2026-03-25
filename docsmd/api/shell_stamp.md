# __skimindex_stamping.sh

Exposes the Python stamp API as shell functions (prefixed `ski_`). They map
boolean returns to POSIX exit codes (True → 0, False → 1), so they work
directly in `if` statements.

Pass `--help` to any function to see the full argument reference:

```bash
ski_needs_run --help
```

## Functions

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

## Example

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
