"""Where the tests look for the code.

The modules live under `src/`, which keeps the project root free of them.
pytest does not know that, so it is told here, once.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
