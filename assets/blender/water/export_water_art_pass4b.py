"""Same validated exporter; versioned candidate output only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import export_water_v3 as E
ROOT=Path(__file__).resolve().parents[3]
E.OUT=ROOT/'apps/client/src/assets/world/water-art-pass4b';E.EV=ROOT/'planning/evidence/water-art-pass4b-20261003'
E.main()
