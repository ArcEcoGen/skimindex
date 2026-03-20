"""
python -m skimindex.stamp

Without arguments: prints bash wrapper functions for all @bash_export-tagged
functions in skimindex.stamp, ready to be eval'd::

    eval "$(python3 -m skimindex.stamp)"

With arguments: dispatches to a specific stamping function::

    python3 -m skimindex.stamp is_stamped /some/output/dir
    python3 -m skimindex.stamp needs_run /some/path src1 src2 --dry-run --label human

Boolean return values are mapped to POSIX exit codes (True → 0, False → 1),
so the wrappers can be used directly in bash ``if`` statements::

    if ski_is_stamped "$output_dir"; then
        echo "already done"
    fi
"""

import sys
import skimindex.stamp as _stamp_module
from skimindex.bashwrapper import generate_bash, dispatch


def main() -> int:
    if len(sys.argv) < 2:
        print(generate_bash(_stamp_module, prefix="ski"))
        return 0

    fn_name = sys.argv[1]
    argv    = sys.argv[2:]
    return dispatch(_stamp_module, fn_name, argv, prefix="ski")


if __name__ == "__main__":
    sys.exit(main())
