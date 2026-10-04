#!/usr/bin/env python3
"""Dependency bootstrap. Defaults to read-only; never guesses project versions."""
import argparse, json, shutil, subprocess, sys
from pathlib import Path

def plan(root, dirs):
    commands=[]; problems=[]; found=False
    for name in dirs:
        p=(root/name).resolve()
        if not p.is_relative_to(root):
            problems.append('Project directory escapes repository: '+name); continue
        if (p/'package.json').is_file():
            found=True
            try: data=json.loads((p/'package.json').read_text())
            except (ValueError,OSError) as e:
                problems.append('Invalid package.json: '+name); continue
            locks=[x for x in ['package-lock.json','pnpm-lock.yaml','yarn.lock'] if (p/x).is_file()]
            if len(locks)!=1:
                problems.append('Need exactly one supported lockfile at '+name); continue
            manager={'package-lock.json':'npm','pnpm-lock.yaml':'pnpm','yarn.lock':'yarn'}[locks[0]]
            pinned=data.get('packageManager','')
            if pinned and pinned.split('@')[0]!=manager:
                problems.append('packageManager/lock mismatch at '+name); continue
            if manager=='yarn':
                problems.append('Yarn project: follow its pinned version and documented immutable install command at '+name); continue
            cmd=['npm','ci'] if manager=='npm' else ['pnpm','install','--frozen-lockfile']
            commands.append((p,cmd))
        if (p/'Cargo.toml').is_file():
            found=True
            if not (p/'Cargo.lock').is_file():
                problems.append('Cargo.lock absent at '+name+'; select the Rust workspace root')
            else: commands.append((p,['cargo','fetch','--locked']))
    if not found: problems.append('No game manifests found. Import existing source first; do not scaffold a replacement.')
    return commands,problems

def main():
    a=argparse.ArgumentParser(); a.add_argument('--install',action='store_true'); a.add_argument('--project-dir',action='append')
    args=a.parse_args(); root=Path.cwd().resolve()
    commands,problems=plan(root,args.project_dir or ['.','client','frontend','server','backend'])
    for tool in ['node','npm','pnpm','cargo','rustc','blender']:
        print(tool+': '+('available' if shutil.which(tool) else 'missing'))
    for p,c in commands:
        print('PLAN',str(p.relative_to(root)), ' '.join(c))
        if not shutil.which(c[0]): problems.append('Required executable missing: '+c[0])
    for problem in problems: print('BLOCKED:',problem)
    if problems: return 2
    if not args.install:
        print('CHECK ONLY. No dependencies installed or game tests run.'); return 0
    for p,c in commands:
        result=subprocess.run(c,cwd=p,check=False)
        if result.returncode: return result.returncode
    print('Dependency install/fetch completed. Game build, browser QA and tests still required.')
    return 0
if __name__=='__main__': sys.exit(main())
