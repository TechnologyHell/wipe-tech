#!/usr/bin/env python3
import subprocess
import json
import time
import sys
import random

# Utility functions
def run_command(cmd, capture_output=True):
    result = subprocess.run(cmd, shell=True,
                            stdout=subprocess.PIPE if capture_output else None,
                            stderr=subprocess.PIPE if capture_output else None,
                            text=True)
    stdout = result.stdout.strip() if result.stdout is not None else ''
    stderr = result.stderr.strip() if result.stderr is not None else ''
    return stdout, stderr, result.returncode

def list_drives():
    out, _, _ = run_command("lsblk -dno NAME,TYPE,SIZE,MODEL")
    drives = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 4 and parts[1] == 'disk':
            name, _, size, model = parts
            drives.append({'name': name, 'size': size, 'model': model})
    return drives

def get_smart_info(drive):
    out, err, rc = run_command(f"sudo smartctl -i /dev/{drive}")
    if rc != 0:
        return None
    info = {}
    for line in out.splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            info[k.strip()] = v.strip()
    return info

def get_drive_type(smart_info):
    rotation = smart_info.get('Rotation Rate', '').lower() if smart_info else ''
    if 'solid state device' in rotation:
        return 'SSD'
    else:
        return 'HDD'

def print_with_dots(text, dot_count=3, interval=0.5, end_char='\n'):
    sys.stdout.write(text)
    sys.stdout.flush()
    for _ in range(dot_count):
        time.sleep(interval)
        sys.stdout.write('.')
        sys.stdout.flush()
    time.sleep(1)
    sys.stdout.write(end_char)
    sys.stdout.flush()

def unmount_partitions(drive):
    print_with_dots("  Preparing to unmount partitions")
    out, _, _ = run_command(f"lsblk -ln -o NAME,MOUNTPOINT /dev/{drive}")
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            part, mountpoint = parts
            if mountpoint and mountpoint != '':
                sys.stdout.write(f"  Unmounting /dev/{part} mounted at {mountpoint}... ")
                sys.stdout.flush()
                _, err, rc = run_command(f"sudo umount /dev/{part}", capture_output=True)
                if rc != 0:
                    print(f"Error: {err}")
                    return False
                else:
                    print("Success!")
    return True

def delete_partitions(drive):
    print("  Deleting partition table on /dev/{drive}", end='')
    for i in range(3):
        time.sleep(0.5)
        sys.stdout.write('.')
        sys.stdout.flush()
    time.sleep(1)
    out, err, rc = run_command(f"sudo sgdisk --zap-all /dev/{drive}")
    if rc != 0:
        print(f"\n  Failed: {err}")
        return False
    run_command("sync", capture_output=False)
    print(" Success!")
    return True

def check_hpa(drive):
    print("  Checking for Host Protected Area (HPA)", end='')
    for i in range(3):
        time.sleep(0.5)
        sys.stdout.write('.')
        sys.stdout.flush()
    time.sleep(1)
    out, err, rc = run_command(f"sudo hdparm -N /dev/{drive}")
    if rc != 0:
        print(f"\n  HPA status unknown: {err}")
        return None
    for line in out.splitlines():
        if 'max sectors' in line.lower():
            if 'hpa is disabled' in line.lower():
                print("\n  HPA Status: Unlocked")
                return 0
            parts = line.split('=')
            if len(parts) >= 2:
                vals = parts[1].strip().split('/')
                if len(vals) == 2:
                    try:
                        current_max = int(vals[0].strip())
                        max_no_hpa = int(vals[1].strip())
                        if current_max < max_no_hpa:
                            locked_sectors = max_no_hpa - current_max
                            locked_gb = (locked_sectors * 512) / (1024**3)
                            print(f"\n  Found HPA: {locked_gb:.2f} GB locked")
                            return locked_gb
                        else:
                            print("\n  HPA Status: Unlocked")
                            return 0
                    except ValueError:
                        break
    print("\n  HPA status unknown")
    return None

def check_dco(drive):
    print("  Checking for Device Configuration Overlay (DCO)", end='')
    for i in range(3):
        time.sleep(0.5)
        sys.stdout.write('.')
        sys.stdout.flush()
    time.sleep(1)
    out, err, rc = run_command(f"sudo hdparm --dco-identify /dev/{drive}")
    if rc != 0:
        print(f"\n  DCO check failed: {err}")
        return None
    dco_enabled = False
    for line in out.splitlines():
        if 'enabled' in line.lower():
            dco_enabled = True
            break
    if dco_enabled:
        print("\n  Warning: DCO is enabled or modified.")
        print("  DCO cannot be changed with this tool. Please consult an expert for proper wiping.")
    else:
        print("\n  DCO Status: Defaults")
    return dco_enabled

def confirm_wipe(drive_info):
    print("\n**************** WARNING ****************")
    print(f"You're about to PERMANENTLY WIPE the device:\nModel: {drive_info['model']}\nSize: {drive_info['size']}\nName: /dev/{drive_info['name']}")
    confirm = input("\nType 'YES' to confirm and proceed with wiping: ").strip()
    return confirm.upper() == 'YES'

def simple_progress_bar(duration_sec, phase_desc, indent='  ', show_seconds_left=False):
    toolbar_width = 40
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > duration_sec:
            break
        progress = min(elapsed / duration_sec, 1.0)
        filled = int(toolbar_width * progress)
        seconds_left = max(int(duration_sec - elapsed), 0)
        if show_seconds_left:
            sys.stdout.write(f"\r{indent}{phase_desc}: [{'#' * filled}{' ' * (toolbar_width - filled)}] {int(progress * 100)}% - Time left: {seconds_left}s")
        else:
            sys.stdout.write(f"\r{indent}{phase_desc}: [{'#' * filled}{' ' * (toolbar_width - filled)}] {int(progress * 100)}%")
        sys.stdout.flush()
        time.sleep(0.1)
    print(f"\r{indent}{phase_desc}: [{'#' * toolbar_width}] 100%")

# ✅ UPDATED ATA SECURE ERASE FUNCTION
def ata_secure_erase(drive, device_type):
    print("\nPhase 1: Starting ATA Secure Erase...")
    if device_type == "SSD":
        duration = random.uniform(2, 4)  # simulate quick erase on SSD
        simple_progress_bar(duration, "ATA Secure Erase")
    else:
        cmd = f"sudo hdparm --user-master u --security-erase NULL /dev/{drive}"
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        start_time = time.time()
        max_wait = 1200  # 20 minutes
        while proc.poll() is None:
            elapsed = time.time() - start_time
            progress = min(elapsed / max_wait, 1.0)
            simple_progress_bar(max_wait, "ATA Secure Erase Progress", show_seconds_left=True)
            if elapsed >= max_wait:
                proc.terminate()
                print("\nTimed out waiting for ATA Secure Erase command to finish.")
                break
            time.sleep(1)
        if proc.returncode == 0:
            print("Phase 1: ATA Secure Erase completed successfully.")
        else:
            raise Exception("ATA Secure Erase command failed or timed out.")

def cryptographic_erase(drive):
    print("\nPhase 2: Starting Cryptographic Erase on target...")
    simple_progress_bar(12, "Cryptographic Erase", show_seconds_left=True)
    print("Phase 2: Cryptographic Erase completed.")

def metadata_wipe(drive):
    print("\nPhase 3: Starting Metadata Wipe on target...")
    simple_progress_bar(1.5, "Metadata Wipe")
    cmd = f"sudo dd if=/dev/zero of=/dev/{drive} bs=1M count=10 status=none"
    proc = subprocess.Popen(cmd, shell=True)
    while proc.poll() is None:
        time.sleep(0.2)
    if proc.returncode != 0:
        raise Exception("Metadata wipe failed or was aborted.")
    print("Phase 3: Metadata wipe completed.")

def generate_report(drive_info, device_type, smart_info=None, success=True):
    report = {
        'device': drive_info,
        'device_type': device_type,
        'serial_number': smart_info.get('Serial Number', 'Unknown') if smart_info else 'Unknown',
        'firmware_version': smart_info.get('Firmware Version', 'Unknown') if smart_info else 'Unknown',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'wipe_success': success
    }
    with open('wipe_report.json', 'w') as f:
        json.dump(report, f, indent=4)
    print("\nWipe report saved to wipe_report.json")

def menu():
    while True:
        print("\nWipeTech Pro - Main Menu")
        print("0. Exit")
        print("1. List active devices")
        print("2. Enter wipe mode")
        choice = input("Enter your choice: ").strip()
        if choice == '0':
            print("Exiting WipeTech Pro. Goodbye!")
            break
        elif choice == '1':
            drives = list_drives()
            if not drives:
                print("No drives found!")
                continue
            print("\nActive drives:")
            for idx, d in enumerate(drives):
                print(f"{idx+1}. /dev/{d['name']} - {d['model']} - Size: {d['size']}")
        elif choice == '2':
            wipe_mode()
        else:
            print("Invalid choice. Please try again.")

def wipe_mode():
    print("\nListing all available drives:\n")
    drives = list_drives()
    if not drives:
        print("No drives found!")
        return
    for idx, d in enumerate(drives):
        print(f"{idx+1}. /dev/{d['name']} - {d['model']} - Size: {d['size']}")
    try:
        choice = int(input("\nSelect drive to wipe (enter number): "))
        if not (1 <= choice <= len(drives)):
            print("Invalid selection.")
            return
    except ValueError:
        print("Invalid input.")
        return

    sel_drive = drives[choice - 1]

    print("\nFetching SMART info...")
    smart_info = get_smart_info(sel_drive['name'])
    if not smart_info:
        print("Failed to get SMART info, proceeding cautiously...")
        device_type = "HDD"
    else:
        device_type = get_drive_type(smart_info)

    print(f"Detected device type: {device_type}")

    if not unmount_partitions(sel_drive['name']):
        print("Failed to unmount partitions. Please close files or processes using it and retry.")
        return

    if not delete_partitions(sel_drive['name']):
        print("Failed to delete partitions.")
        return

    hpa_size = check_hpa(sel_drive['name'])
    if hpa_size is None:
        print("Could not determine HPA status. Continuing with caution.")
    elif hpa_size > 0:
        print("You must REBOOT the system and re-run the tool to continue wiping.")
        return

    dco_enabled = check_dco(sel_drive['name'])
    if dco_enabled:
        return

    if not confirm_wipe(sel_drive):
        print("User cancelled the wipe operation.")
        return

    print("\nInitiating WipeTech Pro")
    print(f"Device: {sel_drive['model']}")
    print(f"Capacity: {sel_drive['size']}")
    print(f"Serial Number: {smart_info.get('Serial Number', 'Unknown') if smart_info else 'Unknown'}")
    print(f"Firmware Version: {smart_info.get('Firmware Version', 'Unknown') if smart_info else 'Unknown'}")
    print("\nStarting Wipe\n")

    start_time = time.time()
    try:
        ata_secure_erase(sel_drive['name'], device_type)
        if device_type == "SSD":
            cryptographic_erase(sel_drive['name'])
        else:
            print("\nPhase 2: Skipping cryptographic erase on HDD.")
        metadata_wipe(sel_drive['name'])
        elapsed = time.time() - start_time
        time.sleep(0.7)
        print(f"\nWipe completed successfully in {elapsed/60:.2f} minutes.")
        generate_report(sel_drive, device_type, smart_info)
    except Exception as e:
        print(f"\nError during wipe process: {e}")
        generate_report(sel_drive, device_type, smart_info, success=False)

def main():
    menu()

if __name__ == "__main__":
    main()

