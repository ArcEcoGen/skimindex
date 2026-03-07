"""Make skimindex package executable via python -m skimindex.

Delegates to the download orchestration CLI.
"""

import sys
from skimindex._download import main

if __name__ == "__main__":
    sys.exit(main())
