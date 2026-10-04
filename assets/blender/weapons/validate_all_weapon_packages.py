"""One headless Blender process for all selected weapon re-import reviews."""
import argparse, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import validate_weapon_packages

parser=argparse.ArgumentParser();parser.add_argument('--jobs',required=True,help='Comma-separated hero:revision pairs, e.g. 02:r2,03:r2,04:r1')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
for job in args.jobs.split(','):
 hero,revision=job.split(':',1)
 sys.argv=[__file__,'--','--hero',hero,'--revision',revision]
 validate_weapon_packages.main()
