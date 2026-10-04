"""Corrected source threshold and decoded-runtime views in one bounded CPU lease."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from np_craft_review import review
review('threshold',7,'game,close,night',decoded=False)
for group in ('flora','croft','pier','threshold','market','skiff'):
    review(group,8,'game,close,night',decoded=True)
