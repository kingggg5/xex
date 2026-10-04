"""Windows bounded H03 diagnose runner. Execute only after root's CPU GO.
One source import, no render/apply.30s timeout,768MiB working-set cap,
stable4.2GiB prelaunch and continuous3GiB free-RAM floor. Stops own PID only.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

GIB=1024**3


class MemoryStatus(ctypes.Structure):
    _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD),('total_physical',ctypes.c_ulonglong),
              ('available_physical',ctypes.c_ulonglong),('total_page',ctypes.c_ulonglong),
              ('available_page',ctypes.c_ulonglong),('total_virtual',ctypes.c_ulonglong),
              ('available_virtual',ctypes.c_ulonglong),('available_extended_virtual',ctypes.c_ulonglong)]


class ProcessMemory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('page_fault_count',wintypes.DWORD),
              ('peak_working_set',ctypes.c_size_t),('working_set',ctypes.c_size_t),
              ('quota_peak_paged',ctypes.c_size_t),('quota_paged',ctypes.c_size_t),
              ('quota_peak_nonpaged',ctypes.c_size_t),('quota_nonpaged',ctypes.c_size_t),
              ('pagefile',ctypes.c_size_t),('peak_pagefile',ctypes.c_size_t)]


def free_ram():
    status=MemoryStatus();status.length=ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError('Cannot verify physical RAM')
    return status.available_physical


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--run',required=True);parser.add_argument('--root-cpu-go',action='store_true')
    args=parser.parse_args()
    if os.name!='nt' or not args.root_cpu_go:raise RuntimeError('Requires Windows and current explicit root CPU GO')
    out=args.out.resolve()
    if out.name!='20261004-hero03-form-r01' or not args.run.replace('-','').replace('_','').isalnum():
        raise RuntimeError('Use the authorized output root and bounded new run name')
    if (out/args.run).exists():raise RuntimeError('Candidate run already exists')
    monitor=out/(args.run+'-monitor')
    if monitor.exists():raise RuntimeError('Monitor receipt already exists')
    monitor.mkdir(parents=True)
    recipe=Path(__file__).with_name('form_repair_r01.py').resolve()
    blender=Path(r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe')
    report={'schema':'xexoria.hero03.form-diagnose-resources/1','mode':'diagnose','render':False,
            'limits':{'seconds':30,'threads':2,'working_set_bytes':768*1024**2,'prelaunch_free_bytes':int(4.2*GIB),
                      'continuous_free_bytes':3*GIB},'status':'PRECHECK','pid':None}
    process=None;handle=None
    kernel=ctypes.windll.kernel32;psapi=ctypes.windll.psapi
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessMemory),wintypes.DWORD]
    try:
        before=[free_ram()];time.sleep(.5);before.append(free_ram());report['prelaunch_samples']=before
        if min(before)<4.2*GIB:
            report['status']='PRELAUNCH_RAM_FLOOR_ABORT';return
        command=[str(blender),'--background','--factory-startup','--disable-autoexec','--threads','2',
                 '--python-exit-code','1','--python',str(recipe),'--','--source',str(args.source.resolve()),
                 '--out',str(out),'--run',args.run,'--mode','diagnose']
        report['command']=command
        with (monitor/'stdout.log').open('wb') as stdout,(monitor/'stderr.log').open('wb') as stderr:
            started=time.monotonic()
            process=subprocess.Popen(command,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
            report['pid']=process.pid;handle=kernel.OpenProcess(0x0400|0x0010,False,process.pid)
            if not handle:raise OSError('Cannot verify own Blender working set')
            peak=0;minimum=min(before);reason=None
            while process.poll() is None:
                available=free_ram();minimum=min(minimum,available)
                counters=ProcessMemory();counters.cb=ctypes.sizeof(counters)
                if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):
                    if process.poll() is not None:break
                    raise OSError('Cannot sample own Blender memory')
                peak=max(peak,counters.working_set)
                if available<3*GIB:reason='CONTINUOUS_RAM_FLOOR'
                elif counters.working_set>768*1024**2:reason='WORKING_SET_CAP'
                elif time.monotonic()-started>30:reason='TIMEOUT'
                if reason:
                    process.terminate();process.wait(timeout=5);break
                time.sleep(.25)
            report.update({'status':'GUARD_STOP' if reason else 'PROCESS_ENDED','stop_reason':reason,
                           'exit_code':process.returncode,'elapsed_seconds':time.monotonic()-started,
                           'peak_working_set_bytes':peak,'minimum_free_RAM_bytes':minimum})
    except Exception as error:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=5)
        report.update({'status':'FAILED','error':str(error)})
        raise
    finally:
        if handle:kernel.CloseHandle(handle)
        (monitor/'resources.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
