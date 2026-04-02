import os
import sys
import time
import ctypes
import msvcrt
import subprocess
import json
import logging
from ctypes import wintypes

# Setup logging
logging.basicConfig(filename="wipe.log", level=logging.DEBUG,
                    format="%(asctime)s [%(levelname)s] %(message)s")

# Windows constants
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2

# Structure for IOCTL_DISK_GET_LENGTH_INFO
IOCTL_DISK_GET_LENGTH_INFO = 0x7405C
class GET_LENGTH(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ulonglong)]


def list_disks():
    """Get available disks using PowerShell Get-Disk."""
    ps_cmd = "Get-Disk | Select Number,FriendlyName,Size | ConvertTo-Json"
    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        capture_output=True, text=True
    )
    try:
        disks = json.loads(result.stdout)
        if isinstance(disks, dict):  # single disk
            disks = [disks]
        return disks
    except Exception as e:
        logging.error(f"Failed to parse disk info: {e}")
        return []


def get_drive_size(drive_number: int) -> int:
    """Return drive size in bytes using DeviceIoControl."""
    GENERIC_READ = 0x80000000
    handle = ctypes.windll.kernel32.CreateFileW(
        f"\\\\.\\PhysicalDrive{drive_number}",
        GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        logging.error(f"CreateFile failed for PhysicalDrive{drive_number}")
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
    if res:
        return length.Length
    else:
        logging.warning(f"DeviceIoControl returned 0 for PhysicalDrive{drive_number}")
        return 0


def wipe_drive(drive_number: int, passes: int = 1, zero: bool = False):
    """Overwrite the selected disk with zeros or random data."""
    drive_path = f"\\\\.\\PhysicalDrive{drive_number}"
    size = get_drive_size(drive_number)

    if size == 0:
        print("[!] Could not detect drive size.")
        return

    print(f"[*] Wiping {drive_path} | Size: {size / (1024**3):.2f} GB")
    logging.info(f"Starting wipe on {drive_path}, size={size}, passes={passes}, zero={zero}")

    handle = ctypes.windll.kernel32.CreateFileW(
        drive_path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        print("[!] Could not open drive. Run as Administrator.")
        logging.error("CreateFile failed (GENERIC_WRITE)")
        return

    chunk_size = 1024 * 1024  # 1 MB
    written = wintypes.DWORD(0)

    for p in range(1, passes + 1):
        print(f"    Pass {p}/{passes}...")
        logging.info(f"Pass {p} started")

        bytes_written = 0
        start_time = time.time()

        while bytes_written < size:
            to_write = min(chunk_size, size - bytes_written)
            # regenerate buffer each pass
            buffer = (b"\x00" * to_write) if zero else os.urandom(to_write)

            success = ctypes.windll.kernel32.WriteFile(
                handle, buffer, to_write, ctypes.byref(written), None
            )
            if not success:
                logging.error(f"WriteFile failed at {bytes_written} bytes on pass {p}")
                break

            bytes_written += written.value

            # progress bar + ETA
            percent = bytes_written / size
            elapsed = time.time() - start_time
            speed = bytes_written / elapsed if elapsed > 0 else 0
            eta = (size - bytes_written) / speed if speed > 0 else 0
            bar_len = 30
            bar = "=" * int(percent * bar_len) + "-" * (bar_len - int(percent * bar_len))
            sys.stdout.write(
                f"\r[{bar}] {percent*100:5.1f}% | {bytes_written//(1024*1024)} MB written | ETA: {int(eta)}s"
            )
            sys.stdout.flush()

            # interrupt check
            if msvcrt.kbhit() and msvcrt.getch().lower() == b"x":
                print("\n[!] Wipe interrupted by user.")
                logging.warning("Wipe interrupted by user")
                ctypes.windll.kernel32.CloseHandle(handle)
                return

        print(f"\n    Completed pass {p}")
        logging.info(f"Pass {p} completed, wrote {bytes_written} bytes")

    ctypes.windll.kernel32.CloseHandle(handle)
    print("[+] Wipe completed successfully.")
    logging.info("Wipe completed successfully")


def main():
    while True:
        print("\n--- Secure Drive Wiper CLI ---")
        print("1. List drives")
        print("2. Wipe a drive")
        print("3. Exit")
        choice = input("Enter choice: ").strip()

        if choice == "1":
            disks = list_disks()
            print("\n--- Available Drives ---\n")
            print(f"{'Number':>6} {'FriendlyName':<25} {'SizeGB':>8}")
            print(f"{'-'*6} {'-'*25} {'-'*8}")
            for d in disks:
                print(f"{d['Number']:>6} {d['FriendlyName']:<25} {int(d['Size'])/(1024**3):8.2f}")

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

            confirm = input(
                f"WARNING: This will ERASE ALL DATA on PhysicalDrive{drive_number}. Type 'YES' to confirm: "
            )
            if confirm != "YES":
                print("Cancelled.")
                continue

            passes = input("Number of passes [default 1]: ").strip()
            passes = int(passes) if passes.isdigit() else 1
            zero = input("Fill with zeros instead of random? (y/N): ").strip().lower() == "y"

            print("[*] Press X at any time to stop the wipe.")
            wipe_drive(drive_number, passes, zero)

        elif choice == "3":
            print("Exiting...")
            break

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
