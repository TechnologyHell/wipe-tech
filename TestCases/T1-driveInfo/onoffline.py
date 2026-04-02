import os
import ctypes
import subprocess
from ctypes import wintypes

# Windows constants
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2

# IOCTL to get drive length
IOCTL_DISK_GET_LENGTH_INFO = 0x7405C

class GET_LENGTH(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ulonglong)]

def run_powershell(cmd):
    """Run a PowerShell command and return (exitcode, stdout, stderr)."""
    result = subprocess.run(
        ["powershell", "-Command", cmd],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()

def set_disk_offline(disk_number, offline=True):
    state = "$true" if offline else "$false"
    try:
        cmd = f"Get-Disk {disk_number} | Set-Disk -IsOffline {state}"
        subprocess.run(["powershell", "-Command", cmd], check=True, capture_output=True)
        print(f"[*] Disk {disk_number} {'offline' if offline else 'online'}")
    except subprocess.CalledProcessError as e:
        print(f"[!] Failed to set disk state: {e.stderr.decode(errors='ignore')}")

def set_disk_online(disk_number: int):
    print(f"[*] Bringing Disk {disk_number} back online...")
    code, out, err = run_powershell(
        f"Get-Disk {disk_number} | Set-Disk -IsOffline $false -Confirm:$false"
    )
    if code == 0:
        print(f"[+] Disk {disk_number} is now online again")
    else:
        print(f"[!] Failed to bring disk online: {err}")

def get_drive_size(drive_number: int) -> int:
    """Return drive size in bytes using DeviceIoControl"""
    GENERIC_READ = 0x80000000
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

def wipe_drive(drive_number: int, passes: int = 1, zero: bool = False):
    """Overwrite the selected disk with zeros or random data"""
    drive_path = f"\\\\.\\PhysicalDrive{drive_number}"
    size = get_drive_size(drive_number)

    if size == 0:
        print("[!] Could not detect drive size.")
        return

    print(f"[*] Wiping {drive_path} | Size: {size / (1024**3):.2f} GB")

    handle = ctypes.windll.kernel32.CreateFileW(
        drive_path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        print("[!] Could not open drive. Run as Administrator.")
        return

    chunk_size = 1024 * 1024  # 1 MB
    buffer = (b"\x00" * chunk_size) if zero else os.urandom(chunk_size)

    written = wintypes.DWORD(0)
    for p in range(1, passes + 1):
        print(f"    Pass {p}/{passes}...")
        bytes_written = 0
        while bytes_written < size:
            to_write = min(chunk_size, size - bytes_written)
            ctypes.windll.kernel32.WriteFile(
                handle, buffer, to_write, ctypes.byref(written), None
            )
            bytes_written += written.value
            # simple progress (every ~100MB)
            if bytes_written % (100 * 1024 * 1024) < chunk_size:
                print(f"      {bytes_written / (1024**2):.0f} MB written...", end="\r")
        print(f"    Completed pass {p}")

    ctypes.windll.kernel32.CloseHandle(handle)
    print("[+] Wipe completed successfully.")

def main():
    while True:
        print("\n--- Secure Drive Wiper CLI ---")
        print("1. List drives")
        print("2. Wipe a drive")
        print("3. Exit")
        choice = input("Enter choice: ").strip()

        if choice == "1":
            for i in range(10):  # scan up to 10 drives
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

            confirm = input(
                f"WARNING: This will ERASE ALL DATA on PhysicalDrive{drive_number} "
                f"({size / (1024**3):.2f} GB).\n"
                "Type 'YES' to confirm: "
            )
            if confirm != "YES":
                print("Cancelled.")
                continue

            passes = input("Number of passes [default 1]: ").strip()
            passes = int(passes) if passes.isdigit() else 1
            zero = input("Fill with zeros instead of random? (y/N): ").strip().lower() == "y"

            # Take disk offline, wipe, then bring it back online
            set_disk_offline(drive_number)
            try:
                wipe_drive(drive_number, passes, zero)
            finally:
                set_disk_online(drive_number)

        elif choice == "3":
            print("Exiting...")
            break

        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
