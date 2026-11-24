import sys
from pathlib import Path

# Add be to sys.path
be_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(be_dir))

try:
    from src.main import app
    print("SUCCESS: src.main app loaded cleanly!")
    print(f"Registered routes: {len(app.routes)}")
    for r in app.routes[:5]:
        print(f"  Route: {getattr(r, 'path', str(r))}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

