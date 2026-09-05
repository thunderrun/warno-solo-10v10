"""Apply an experimental, exact-build WARNO lobby patch in RAM only.

Defaults to read-only status. Call with --pid <observed PID> --apply only while
WARNO is at the Solo menu. Restart WARNO to remove the patch before multiplayer.
No game executable or profile is written by this script.
"""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime
import hashlib
import json
from project_config import load_config

ROOT = Path(__file__).resolve().parent
EXE = Path(load_config()['game_exe'])
EXPECTED_SHA = "70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8"
EXPECTED_SIZE = 55736360
RVA = 0x013A6CB1
FILE_OFFSET = 0x013A60B1
FUNCTION_START = 0x013A6C70
FUNCTION_END = 0x013A6F55
ORIGINAL = bytes.fromhex("8b 7f 1c")
PATCH = bytes.fromhex("6a 14 5f")
CONTEXT = bytes.fromhex("8b7f1c4c8d76484c89f189fae82ebd0000b910000000e83436cafe48c700010000")

kernel = C.WinDLL("kernel32", use_last_error=True)
psapi = C.WinDLL("psapi", use_last_error=True)
kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel.OpenProcess.restype = W.HANDLE
kernel.CloseHandle.argtypes = [W.HANDLE]
kernel.CloseHandle.restype = W.BOOL
kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
kernel.QueryFullProcessImageNameW.restype = W.BOOL
kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
kernel.ReadProcessMemory.restype = W.BOOL
kernel.WriteProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
kernel.WriteProcessMemory.restype = W.BOOL
kernel.VirtualProtectEx.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD, C.POINTER(W.DWORD)]
kernel.VirtualProtectEx.restype = W.BOOL
kernel.FlushInstructionCache.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t]
kernel.FlushInstructionCache.restype = W.BOOL
kernel.CheckRemoteDebuggerPresent.argtypes = [W.HANDLE, C.POINTER(W.BOOL)]
kernel.CheckRemoteDebuggerPresent.restype = W.BOOL
psapi.EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(C.c_void_p), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
psapi.EnumProcessModulesEx.restype = W.BOOL


def require(ok, what):
    if not ok:
        raise RuntimeError(f"{what}: {C.WinError(C.get_last_error())}")


def read(handle, address, size):
    data = C.create_string_buffer(size)
    count = C.c_size_t()
    require(kernel.ReadProcessMemory(handle, address, data, size, C.byref(count)), "ReadProcessMemory")
    if count.value != size:
        raise RuntimeError("Incomplete memory read")
    return data.raw


def write(handle, address, data):
    count = C.c_size_t()
    buf = C.create_string_buffer(data)
    require(kernel.WriteProcessMemory(handle, address, buf, len(data), C.byref(count)), "WriteProcessMemory")
    if count.value != len(data):
        raise RuntimeError("Incomplete memory write")
    require(kernel.FlushInstructionCache(handle, address, len(data)), "FlushInstructionCache")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError("A 64-bit Python runtime is required")

    disk = EXE.read_bytes()
    sha_before = hashlib.sha256(disk).hexdigest()
    if len(disk) != EXPECTED_SIZE or sha_before != EXPECTED_SHA:
        raise RuntimeError("Unsupported executable; nothing changed")
    if disk[FILE_OFFSET:FILE_OFFSET+len(CONTEXT)] != CONTEXT:
        raise RuntimeError("Disk instruction context mismatch")

    access = 0x0400 | 0x0010  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    if args.apply:
        access |= 0x0020 | 0x0008  # PROCESS_VM_WRITE | PROCESS_VM_OPERATION
    handle = kernel.OpenProcess(access, False, args.pid)
    require(handle, "OpenProcess")
    try:
        path_buffer = C.create_unicode_buffer(32768)
        path_size = W.DWORD(len(path_buffer))
        require(kernel.QueryFullProcessImageNameW(handle, 0, path_buffer, C.byref(path_size)), "Process identity")
        if Path(path_buffer.value).resolve() != EXE.resolve():
            raise RuntimeError("Target process path does not match WARNO.exe")
        debugger = W.BOOL()
        require(kernel.CheckRemoteDebuggerPresent(handle, C.byref(debugger)), "Debugger check")
        if debugger.value:
            raise RuntimeError("Debugger attached; refusing to modify this process")

        modules = (C.c_void_p * 2048)()
        needed = W.DWORD()
        require(psapi.EnumProcessModulesEx(handle, modules, C.sizeof(modules), C.byref(needed), 3), "Module enumeration")
        base = modules[0]
        if not base or read(handle, base, 2) != b"MZ":
            raise RuntimeError("Invalid main-module base")
        address = base + RVA
        raw_start = FILE_OFFSET - (RVA - FUNCTION_START)
        expected_function = disk[raw_start:raw_start+FUNCTION_END-FUNCTION_START]
        actual_function = read(handle, base+FUNCTION_START, len(expected_function))
        patch_offset = RVA - FUNCTION_START
        patched_function = expected_function[:patch_offset] + PATCH + expected_function[patch_offset+3:]
        if actual_function not in (expected_function, patched_function):
            raise RuntimeError("Runtime function differs from the inspected build; nothing changed")

        before = read(handle, address, 3)
        changed = False
        if args.apply and before == ORIGINAL:
            # The caller must ensure WARNO is at the Solo menu. Recheck memory
            # before writing so a concurrent patch is never silently overwritten.
            if read(handle, base+FUNCTION_START, len(expected_function)) != expected_function:
                raise RuntimeError("Function changed during validation")
            old_protect = W.DWORD()
            require(kernel.VirtualProtectEx(handle, address, 3, 0x40, C.byref(old_protect)), "Set writable protection")
            try:
                try:
                    write(handle, address, PATCH)
                    if read(handle, base+FUNCTION_START, len(patched_function)) != patched_function:
                        raise RuntimeError("Patched function read-back failed")
                    changed = True
                except Exception:
                    write(handle, address, ORIGINAL)
                    if read(handle, address, 3) != ORIGINAL:
                        raise RuntimeError("Rollback failed; restart WARNO")
                    raise
            finally:
                ignored = W.DWORD()
                require(kernel.VirtualProtectEx(handle, address, 3, old_protect.value, C.byref(ignored)), "Restore page protection")

        after = read(handle, address, 3)
        sha_after = hashlib.sha256(EXE.read_bytes()).hexdigest()
        if sha_after != sha_before:
            raise RuntimeError("WARNO.exe changed on disk during this operation")
        result = {
            "time": datetime.now().astimezone().isoformat(),
            "pid": args.pid,
            "process_path": path_buffer.value,
            "module_base": hex(base),
            "patch_address": hex(address),
            "before": before.hex(" "),
            "after": after.hex(" "),
            "memory_changed_this_run": changed,
            "memory_patch_active": after == PATCH,
            "whole_function_verified": True,
            "executable_sha256": sha_after,
            "executable_unchanged": True,
            "gameplay_validated": False,
        }
        print(json.dumps(result, indent=2))
        if args.apply:
            out = ROOT / ("runtime-apply-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        kernel.CloseHandle(handle)


if __name__ == "__main__":
    main()
