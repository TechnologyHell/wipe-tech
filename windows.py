import os
import sys
import time
import msvcrt
import ctypes
import subprocess
from ctypes import wintypes

# -----------------------------
# Windows constants
# -----------------------------
GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
IOCTL_DISK_GET_LENGTH_INFO = 0x7405C

# -----------------------------
# Drive size structure
# -----------------------------
class GET_LENGTH(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ulonglong)]

# -----------------------------
# Disk management helpers
# -----------------------------
def run_powershell(cmd: str):
    try:
        result = subprocess.run(
            ["powershell", "-Command", cmd],
            check=True, capture_output=True, text=True
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()

def set_disk_offline(disk_number: int, offline=True):
    state = "$true" if offline else "$false"
    success, out = run_powershell(f"Get-Disk {disk_number} | Set-Disk -IsOffline {state} -ErrorAction Stop")
    if success:
        print(f"[*] Disk {disk_number} {'offline' if offline else 'online'}")
    else:
        print(f"[!] Failed to change disk state: {out}")
    return success

def initialize_and_format(disk_number: int, style="GPT", label="WIPEDISK"):
    print(f"[*] Initializing Disk {disk_number} as {style}...")
    run_powershell(f"Initialize-Disk -Number {disk_number} -PartitionStyle {style} -ErrorAction SilentlyContinue")
    success, out = run_powershell(f"New-Partition -DiskNumber {disk_number} -UseMaximumSize -AssignDriveLetter -ErrorAction Stop")
    if not success:
        print(f"[!] Failed to create partition: {out}")
        return False
    drive_letter = None
    for token in out.split():
        if len(token) == 1 and token.isalpha():
            drive_letter = token
            break
    if not drive_letter:
        print("[!] Could not determine drive letter.")
        return False
    print(f"[*] Formatting {drive_letter}: as NTFS...")
    run_powershell(f"Format-Volume -DriveLetter {drive_letter} -FileSystem NTFS -NewFileSystemLabel {label} -Force -Confirm:$false")
    print(f"[+] Disk {disk_number} ready at {drive_letter}:\\")
    return True

# -----------------------------
# Drive helpers
# -----------------------------
def get_drive_size(drive_number: int) -> int:
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

# -----------------------------
# Wiping logic
# -----------------------------
def wipe_drive(drive_number: int, passes: int = 1, zero: bool = False, init_after=True, chunk_size_mb=4):
    drive_path = f"\\\\.\\PhysicalDrive{drive_number}"
    size = get_drive_size(drive_number)
    if size == 0:
        print("[!] Could not detect drive size.")
        return

    # Take offline first
    if not set_disk_offline(drive_number, True):
        print("[!] Aborting wipe. Cannot take disk offline.")
        return

    handle = ctypes.windll.kernel32.CreateFileW(
        drive_path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        print("[!] Cannot open drive. Run as Administrator.")
        set_disk_offline(drive_number, False)
        return

    buffer = (b"\x00" * (chunk_size_mb * 1024 * 1024)) if zero else os.urandom(chunk_size_mb * 1024 * 1024)
    written = wintypes.DWORD(0)

    try:
        for p in range(1, passes + 1):
            print(f"    Pass {p}/{passes}...")

            # Reset file pointer
            new_pos = ctypes.c_longlong(0)
            ctypes.windll.kernel32.SetFilePointerEx(handle, new_pos, None, 0)

            bytes_written = 0
            start_time = time.time()

            while bytes_written < size:
                to_write = min(chunk_size_mb * 1024 * 1024, size - bytes_written)
                ctypes.windll.kernel32.WriteFile(
                    handle, buffer, to_write, ctypes.byref(written), None
                )
                bytes_written += written.value

                percent = (bytes_written / size) * 100
                elapsed = time.time() - start_time
                speed = bytes_written / elapsed if elapsed > 0 else 0
                eta = (size - bytes_written) / speed if speed > 0 else 0

                bar_len = 30
                filled = int(bar_len * percent / 100)
                bar = "=" * filled + "-" * (bar_len - filled)
                sys.stdout.write(
                    f"\r[{bar}] {percent:5.1f}% | {bytes_written // (1024**2):,} MB written | ETA: {eta:,.0f}s "
                )
                sys.stdout.flush()

                if msvcrt.kbhit() and msvcrt.getch().lower() == b"x":
                    print("\n[!] Interrupted by user.")
                    raise KeyboardInterrupt

            print(f"\n    Completed pass {p}")

    except KeyboardInterrupt:
        print("[!] Wipe aborted by user.")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
        set_disk_offline(drive_number, False)
        if init_after:
            initialize_and_format(drive_number, style="GPT", label="WIPEDISK")
        print("[*] Disk state restored.")

    print("[+] Wipe completed successfully.")

# -----------------------------
# CLI
# -----------------------------
def main():
    while True:
        print("\n--- Secure Drive Wiper CLI ---")
        print("0. Exit")
        print("1. List drives")
        print("2. Wipe a drive")

        choice = input("Enter choice: ").strip()

        if choice == "1":
            for i in range(10):
                size = get_drive_size(i)
                if size > 0:
                    print(f"Drive {i} -> {size / (1024**3):.2f} GB")
            continue

        elif choice == "2":
            drive_number = input("Enter PhysicalDrive number: ").strip()
            if not drive_number.isdigit():
                print("Invalid input.")
                continue
            drive_number = int(drive_number)

            size = get_drive_size(drive_number)
            if size == 0:
                print("Drive not found.")
                continue

            confirm = input(f"WARNING: This will ERASE ALL DATA on PhysicalDrive{drive_number} ({size / (1024**3):.2f} GB).\nType 'YES' to confirm: ")
            if confirm != "YES":
                print("Cancelled.")
                continue

            passes = input("Number of passes [default 1]: ").strip()
            passes = int(passes) if passes.isdigit() else 1
            zero = input("Fill with zeros instead of random? (y/N): ").strip().lower() == "y"

            print("[*] Press X at any time to stop the wipe.")
            wipe_drive(drive_number, passes, zero, init_after=True)

        elif choice == "0":
            print("Exiting...")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
