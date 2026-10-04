"""Exact-runtime decoded final camera and complete kit framing check."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import np_stone_review as V

for group,views in (("sample","game,close,night"),("rocks","lineup"),("cliffs","lineup"),
                    ("grotto","lineup"),("ruins","lineup"),("crystals","close,night")):
    sys.argv=[__file__,"--","--revision","6","--runtime","--group",group,"--views",views]
    V.main()
