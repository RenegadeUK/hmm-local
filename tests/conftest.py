import sys
from pathlib import Path
import os

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("PYTEST_CURRENT_TEST", "1")
