#!/usr/bin/env python3
"""Read-only executable/version report; never reads environment values or credentials."""
import json, shutil, subprocess
TOOLS=['git','node','npm','pnpm','python3','rustc','cargo','blender']
def inspect():
    report={}
    for tool in TOOLS:
        executable=shutil.which(tool)
        if not executable:
            report[tool]={'status':'missing'}; continue
        try:
            p=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=15,check=False)
            line=(p.stdout or p.stderr).splitlines()
            report[tool]={'status':'available' if p.returncode==0 else 'error','version':line[0][:200] if line else '', 'exit_code':p.returncode}
        except (OSError,subprocess.TimeoutExpired): report[tool]={'status':'error'}
    return report
if __name__=='__main__': print(json.dumps(inspect(),indent=2))
