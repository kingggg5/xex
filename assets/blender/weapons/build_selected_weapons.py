"""Build the three selected candidates sequentially in a single Blender slot."""
import argparse,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_hero_weapons

parser=argparse.ArgumentParser();parser.add_argument('--jobs',default='04:r1,02:r2,03:r3')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
for job in args.jobs.split(','):
 hero,revision=job.split(':',1)
 bpy.ops.wm.read_factory_settings(use_empty=False)
 sys.argv=[__file__,'--','--hero',hero,'--revision',revision]
 build_hero_weapons.main()
