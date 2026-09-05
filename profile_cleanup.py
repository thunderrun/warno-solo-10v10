"""Repair only expanded solo lobby settings, after WARNO has exited.

The per-session watcher holds a handle to the actual game process, so PID reuse
cannot trigger premature cleanup. It never writes a profile while WARNO runs.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

from profile_codec import repair
from runtime_10v10 import EXE, EXPECTED_SHA, kernel, psapi
from project_config import load_config

ROOT=Path(__file__).resolve().parent
PROFILE=Path(load_config()['profile'])
kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
kernel.WaitForSingleObject.restype=W.DWORD
kernel.CreateMutexW.argtypes=[C.c_void_p,W.BOOL,W.LPCWSTR]
kernel.CreateMutexW.restype=W.HANDLE
kernel.GetProcessTimes.argtypes=[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)]
kernel.GetProcessTimes.restype=W.BOOL
psapi.EnumProcesses.argtypes=[C.POINTER(W.DWORD),W.DWORD,C.POINTER(W.DWORD)]
psapi.EnumProcesses.restype=W.BOOL

def digest(data):return hashlib.sha256(data).hexdigest()

def process_path(handle):
    buffer=C.create_unicode_buffer(32768);size=W.DWORD(len(buffer))
    if not kernel.QueryFullProcessImageNameW(handle,0,buffer,C.byref(size)):
        raise C.WinError(C.get_last_error())
    return Path(buffer.value)

def game_running():
    ids=(W.DWORD*16384)();needed=W.DWORD()
    if not psapi.EnumProcesses(ids,C.sizeof(ids),C.byref(needed)):
        raise C.WinError(C.get_last_error())
    if needed.value>=C.sizeof(ids):raise RuntimeError('Process enumeration overflow')
    for game_pid in ids[:needed.value//C.sizeof(W.DWORD)]:
        handle=kernel.OpenProcess(0x1000,False,game_pid)
        if not handle:continue
        try:
            try:path=process_path(handle)
            except OSError:continue
            if path.name.lower()=='warno.exe':return True
        finally:kernel.CloseHandle(handle)
    return False

def log(event,**fields):
    entry={'time':datetime.now().astimezone().isoformat(),'event':event,**fields}
    with (ROOT/'profile-cleanup.log').open('a',encoding='utf-8') as out:
        out.write(json.dumps(entry)+'\n')
    return entry

def atomic_json(path,data):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(data,indent=2),encoding='utf-8')
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

def backup_root():
    shell=C.WinDLL('shell32',use_last_error=True)
    shell.SHGetFolderPathW.argtypes=[W.HWND,C.c_int,W.HANDLE,W.DWORD,W.LPWSTR]
    shell.SHGetFolderPathW.restype=C.c_long
    documents=C.create_unicode_buffer(32768)
    if shell.SHGetFolderPathW(None,5,None,0,documents)!=0:
        raise RuntimeError('Cannot locate Documents for the required backup')
    return Path(documents.value)/'WARNO_Profile_Backups'

def repair_file(path=PROFILE):
    if game_running():raise RuntimeError('Close WARNO before repairing its saved lobby.')
    data=path.read_bytes()
    fixed,report=repair(data)
    if fixed==data:return {'changed':False,**report}
    # Use the current file, never an old whole-profile restore. Keep a verified
    # copy of that exact pre-repair file under Documents before any replacement.
    backup_dir=backup_root()/('lobby_cleanup_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup_dir.mkdir(parents=True)
    backup=backup_dir/'PROFILE.before-cleanup.profile2'
    with backup.open('xb') as out:
        out.write(data);out.flush();os.fsync(out.fileno())
    if backup.read_bytes()!=data:raise RuntimeError('Profile backup verification failed')
    temp=path.with_name(path.name+'.10v10-'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as out:
            out.write(fixed);out.flush();os.fsync(out.fileno())
        if temp.read_bytes()!=fixed:raise RuntimeError('Repair staging verification failed')
        # A Steam sync or another WARNO launch must not be overwritten with a
        # stale snapshot. Windows replacement also refuses incompatible locks.
        if game_running():raise RuntimeError('WARNO restarted; saved lobby cleanup deferred')
        if path.read_bytes()!=data:raise RuntimeError('Profile changed during repair; retry needed')
        os.replace(temp,path)
        if path.read_bytes()!=fixed:raise RuntimeError('Profile changed after replacement; check the cleanup log')
    finally:
        if temp.exists():temp.unlink()
    result={'changed':True,'profile':str(path),'backup':str(backup),'before_sha256':digest(data),'after_sha256':digest(fixed),**report}
    (backup_dir/'repair.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    log('profile_repaired',**result)
    return result

def watch(game_pid,ready):
    handle=kernel.OpenProcess(0x100000|0x1000,False,game_pid)
    if not handle:raise C.WinError(C.get_last_error())
    mutex=None
    try:
        if process_path(handle).resolve()!=EXE.resolve():raise RuntimeError('Unexpected game process path')
        if digest(EXE.read_bytes())!=EXPECTED_SHA:raise RuntimeError('Unsupported WARNO build')
        times=[W.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[C.byref(t) for t in times]):raise C.WinError(C.get_last_error())
        born=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        C.set_last_error(0)
        mutex=kernel.CreateMutexW(None,False,f'Local\\WARNO10v10Cleanup_{game_pid}_{born}')
        if not mutex:raise C.WinError(C.get_last_error())
        if C.get_last_error()==183:
            atomic_json(ready,{'ready':True,'already_watching':True,'game_pid':game_pid})
            return
        if kernel.WaitForSingleObject(handle,0)!=258:raise RuntimeError('WARNO has already exited')
        # Parse and prove the cleanup is supported before authorizing a RAM
        # patch. No profile mutation occurs at this stage.
        _,preflight=repair(PROFILE.read_bytes())
        session=ROOT/f'cleanup-session-{game_pid}-{born}.json'
        atomic_json(session,{'status':'watching','game_pid':game_pid,'process_created':born,'profile':str(PROFILE)})
        log('watching',game_pid=game_pid,preflight=preflight)
        atomic_json(ready,{'ready':True,'watcher_pid':os.getpid(),'game_pid':game_pid,'session':str(session)})
        while True:
            state=kernel.WaitForSingleObject(handle,1000)
            if state==0:break
            if state!=258:raise C.WinError(C.get_last_error())
        log('game_exited',game_pid=game_pid)
        # Save completion / Steam synchronization can briefly hold the file.
        # Keep checking for five quiet seconds and retry transient failures.
        deadline=time.monotonic()+30;quiet_since=None;last_error=None;last_hash=None
        while time.monotonic()<deadline:
            try:
                if game_running():raise RuntimeError('WARNO was restarted before cleanup completed')
                before=PROFILE.read_bytes();time.sleep(0.3)
                if before!=PROFILE.read_bytes():raise RuntimeError('Waiting for the final profile save')
                result=repair_file()
                current=digest(PROFILE.read_bytes())
                if current!=last_hash:quiet_since=time.monotonic();last_hash=current
                last_error=None
                if time.monotonic()-quiet_since>=5:
                    atomic_json(session,{'status':'complete','game_pid':game_pid,'last_check':result,'profile_sha256':current})
                    log('cleanup_complete',game_pid=game_pid,profile_sha256=current)
                    return
            except Exception as exc:
                last_error=str(exc);quiet_since=None;last_hash=None
            time.sleep(0.3)
        raise RuntimeError(last_error or 'Saved profile did not settle in time')
    finally:
        if mutex:kernel.CloseHandle(mutex)
        kernel.CloseHandle(handle)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch-pid',type=int)
    parser.add_argument('--ready-file',type=Path)
    parser.add_argument('--repair',action='store_true')
    args=parser.parse_args()
    try:
        if args.watch_pid and args.ready_file:watch(args.watch_pid,args.ready_file)
        elif args.repair:print(json.dumps(repair_file(),indent=2))
        else:parser.error('Choose --repair or --watch-pid PID --ready-file PATH')
        return 0
    except Exception as exc:
        result=log('error',message=str(exc),game_pid=args.watch_pid)
        if args.ready_file and not args.ready_file.exists():atomic_json(args.ready_file,{'ready':False,'error':str(exc)})
        if sys.stderr:print(json.dumps(result),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
