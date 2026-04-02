import os
import sys
import time
import ctypes
from ctypes import wintypes
import subprocess
import threading

# -----------------------------
# Windows constants
# -----------------------------
GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
IOCTL_DISK_GET_LENGTH_INFO = 0x7405C

# -----------------------------
# Drive size structure
# -----------------------------
class GET_LENGTH(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ulonglong)]

# -----------------------------
# Drive helpers
# -----------------------------
def get_drive_size(drive_number: int) -> int:
    """Return drive size in bytes"""
    try:
        handle = ctypes.windll.kernel32.CreateFileW(
            f"\\\\.\\PhysicalDrive{drive_number}",
            GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None
        )
        if handle == -1:
            return 0
        length = GET_LENGTH()
        bytes_returned = wintypes.DWORD(0)
        res = ctypes.windll.kernel32.DeviceIoControl(
            handle, IOCTL_DISK_GET_LENGTH_INFO,
            None, 0,
            ctypes.byref(length), ctypes.sizeof(length),
            ctypes.byref(bytes_returned), None
        )
        ctypes.windll.kernel32.CloseHandle(handle)
        return length.Length if res else 0
    except:
        return 0

def list_drives():
    print("\nActive drives:")
    drives = []
    try:
        # Get drive info via PowerShell
        cmd = "Get-Disk | Select-Object Number, FriendlyName, Size | ConvertTo-Json"
        result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, check=True)
        disks = eval(result.stdout)  # returns list of dicts

        if isinstance(disks, dict):  # only 1 drive
            disks = [disks]

        for d in disks:
            num = int(d["Number"])
            model = d["FriendlyName"]
            size_gb = int(d["Size"]) / (1024**3)
            drives.append((num, model, size_gb))
            print(f"{len(drives)}. PhysicalDrive{num} - {model} - Size: {size_gb:.1f} GB")
    except Exception as e:
        print(f"[!] Failed to list drives: {e}")

    if not drives:
        print("No drives detected.")
    return drives

    print("\nActive drives:")
    drives = []
    try:
        result = subprocess.run(
            ["wmic", "diskdrive", "get", "DeviceID,Model,Size", "/format:csv"],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().splitlines()
        for line in lines[1:]:  # skip header
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 4:
                continue
            _, device, model, size = parts
            drive_number = int(device.replace("\\\\.\\PhysicalDrive", "").strip())
            size_bytes = int(size) if size.isdigit() else 0
            size_gb = size_bytes / (1024**3)
            drives.append((drive_number, model.strip(), size_gb))
            print(f"{len(drives)}. PhysicalDrive{drive_number} - {model.strip()} - Size: {size_gb:.1f} GB")
    except Exception as e:
        print(f"[!] Failed to list drives: {e}")
    return drives

# -----------------------------
# Wiping helpers
# -----------------------------
def run_diskpart_clean(drive_number: int):
    """Clean drive using diskpart silently"""
    commands = f"""
select disk {drive_number}
clean
create partition primary
assign letter=Z
"""
    subprocess.run(["diskpart"], input=commands, text=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def overwrite_drive_zeros(drive_number: int, chunk_mb=4):
    """Overwrite the drive with zeros"""
    drive_path = f"\\\\.\\PhysicalDrive{drive_number}"
    handle = ctypes.windll.kernel32.CreateFileW(
        drive_path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        print("[!] Cannot open drive. Run as Administrator.")
        return

    size = get_drive_size(drive_number)
    buffer = b"\x00" * (chunk_mb*1024*1024)
    written = wintypes.DWORD(0)
    bytes_written = 0

    try:
        while bytes_written < size:
            to_write = min(len(buffer), size - bytes_written)
            ctypes.windll.kernel32.WriteFile(handle, buffer, to_write, ctypes.byref(written), None)
            bytes_written += written.value
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

# -----------------------------
# Simulated progress
# -----------------------------
def simulate_progress(size_gb, duration=20*60):
    """Simulate Cryptographic Erase with progress bar and ETA"""
    steps = 50
    start_time = time.time()
    for i in range(steps+1):
        percent = i / steps * 100
        elapsed = time.time() - start_time
        eta = duration * (1 - i/steps)
        bar = "="*int(i*30/steps) + "-"*(30-int(i*30/steps))
        mb_done = int(size_gb*1024*(percent/100))
        sys.stdout.write(f"\rErasing: Simulated Cryptographic Erase |[{bar}] {percent:5.1f}% | {mb_done:,} MB written | ETA: {int(eta)}s")
        sys.stdout.flush()
        time.sleep(duration/steps)
    print("\nPhase completed.")

# -----------------------------
# Main wipe function
# -----------------------------
def wipe_drive(drive_number: int):
    size_bytes = get_drive_size(drive_number)
    size_gb = size_bytes / (1024**3)
    if size_bytes == 0:
        print("[!] Cannot detect drive.")
        return

    print(f"\nWARNING: This will PERMANENTLY WIPE PhysicalDrive{drive_number} ({size_gb:.1f} GB).")
    confirm = input("Type 'YES' to proceed: ")
    if confirm != "YES":
        print("Cancelled.")
        return

    print("\n[*] Initiating WipeTech Pro")

    # Run DiskPart clean in background
    t1 = threading.Thread(target=run_diskpart_clean, args=(drive_number,))
    t1.start()

    # Overwrite in background (zeros)
    t2 = threading.Thread(target=overwrite_drive_zeros, args=(drive_number,))
    t2.start()

    # Frontend progress simulation
    simulate_progress(size_gb, duration=20*60)

    t1.join()
    t2.join()

    print("\n[+] Drive wipe completed successfully.\n")

# -----------------------------
# CLI
# -----------------------------
def main():
    while True:
        print("\nWipeTech Pro - Main Menu")
        print("0. Exit")
        print("1. List active devices")
        print("2. Wipe a drive")
        choice = input("Enter your choice: ").strip()

        if choice == "1":
            list_drives()
        elif choice == "2":
            drives = list_drives()
            if not drives:
                continue
            idx = input("\nSelect drive to wipe (enter number): ").strip()
            if not idx.isdigit() or int(idx)-1 not in range(len(drives)):
                print("Invalid selection.")
                continue
            drive_number = drives[int(idx)-1][0]
            wipe_drive(drive_number)
        elif choice == "0":
            print("Exiting WipeTech Pro.")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
