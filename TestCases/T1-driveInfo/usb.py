import os
import ctypes
from ctypes import wintypes
import subprocess

# -----------------------------
# Windows constants
# -----------------------------
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3

# -----------------------------
# Wipe volume
# -----------------------------
def wipe_volume(drive_letter, size_mb, chunk_mb=8):
    path = f"\\\\.\\{drive_letter}:"
    handle = ctypes.windll.kernel32.CreateFileW(
        path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        print("[!] Cannot open volume.")
        return
    buf = b"\x00" * (chunk_mb * 1024 * 1024)
    import time
    written_mb = 0
    try:
        while written_mb < size_mb:
            ctypes.windll.kernel32.WriteFile(handle, buf, len(buf), ctypes.byref(wintypes.DWORD(0)), None)
            written_mb += chunk_mb
            print(f"\r{written_mb}/{size_mb} MB written...", end="", flush=True)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    print("\n[+] Wipe done.")

# -----------------------------
# Main wipe routine
# -----------------------------
def wipe_usb(drive_number):
    print(f"[*] Wiping PhysicalDrive{drive_number}...")

    # Step 1: Delete all partitions and create temp partition Z:
    commands = f"""
select disk {drive_number}
clean
create partition primary
assign letter=Z
"""
    subprocess.run(["diskpart"], input=commands, text=True)

    # Step 2: Overwrite with zeros
    # Use size estimation (for small USB, 4GB ~ 4096MB)
    size_mb = int(input("Enter approximate size of USB in MB: "))
    wipe_volume("Z", size_mb)

    # Step 3: Delete partitions again and format final NTFS
    commands = f"""
select disk {drive_number}
clean
create partition primary
format fs=ntfs label=WIPEDISK quick
assign
"""
    subprocess.run(["diskpart"], input=commands, text=True)

    print("[+] USB wipe & format complete.")

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    drive_number = input("Enter PhysicalDrive number of USB: ").strip()
    wipe_usb(int(drive_number))
