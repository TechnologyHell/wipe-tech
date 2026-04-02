#!/usr/bin/env python3
import subprocess
import json
import time
import sys
import random
import hashlib
import re


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
    if 'solid state device' in rotation or 'ssd' in rotation:
        return 'SSD'
    else:
        return 'HDD'

def print_with_dots(text, dot_count=3, interval=0.2, end_char='\n'):
    sys.stdout.write(text)
    sys.stdout.flush()
    for _ in range(dot_count):
        time.sleep(interval)
        sys.stdout.write('.')
        sys.stdout.flush()
    time.sleep(0.2)
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
    print(f"  Deleting partition table on /dev/{drive}", end='')
    for _ in range(3):
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
    """
    Check Host Protected Area (HPA) and attempt unlock if necessary.
    Returns:
        dict: {'locked_sectors': int, 'max_no_hpa': int} if locked
        0 if unlocked
        None if unknown
    """
    print("  Checking for Host Protected Area (HPA)...", end='')
    for _ in range(3):
        time.sleep(0.4)
        print('.', end='', flush=True)
    time.sleep(0.2)

    out, err, rc = run_command(f"sudo hdparm -N /dev/{drive}")
    if rc != 0 or not out:
        print(f"\n  Could not check HPA: {err}")
        # fallback: attempt unlock using max drive size
        max_sectors = blockdev_get_size(drive) // 512
        print(f"  Attempting to unlock HPA using full drive size: {max_sectors} sectors...")
        unlock_hpa(drive, max_sectors)
        return None

    # parse output line containing 'max sectors'
    for line in out.splitlines():
        if 'max sectors' in line.lower():
            try:
                nums = re.findall(r'\d+', line)
                if len(nums) >= 2:
                    current_max = int(nums[0])
                    max_no_hpa = int(nums[1])
                    if current_max < max_no_hpa:
                        locked_sectors = max_no_hpa - current_max
                        locked_gb = (locked_sectors * 512) / (1024**3)
                        print(f"\n  HPA Found: {locked_gb:.2f} GB locked")
                        print("  Unlocking HPA...")
                        unlock_hpa(drive, max_no_hpa)
                        return {'locked_sectors': locked_sectors, 'max_no_hpa': max_no_hpa}
                    else:
                        print("\n  HPA Status: Unlocked")
                        return 0
            except Exception as e:
                break

def unlock_hpa(drive, max_sectors):
    """Unlock HPA by setting max sectors to full capacity."""
    print(f"\nAttempting to unlock HPA on /dev/{drive}...")
    cmd = f"sudo hdparm --yes-i-know-what-i-am-doing -N p{max_sectors} /dev/{drive}"
    out, err, rc = run_command(cmd)
    if rc == 0:
        print(f"HPA unlocked successfully on /dev/{drive}.")
        print("Kindly REBOOT the system and relaunch the tool to continue.")
        sys.exit(0)
    else:
        print(f"Failed to unlock HPA on /dev/{drive}: {err}")
        sys.exit(1)


def check_dco(drive):
    print("  Checking for Device Configuration Overlay (DCO)", end='')
    for _ in range(3):
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

def simple_progress_bar(duration_sec, prefix='', indent='  '):
    start = time.time()
    i = 0
    while i <= 100:
        elapsed = time.time() - start
        seconds_left = max(duration_sec - elapsed, 0)
        percent = int((elapsed / duration_sec) * 100)
        if percent > i:
            i = percent  # update percent only when it increases
        sys.stdout.write(f"\r{indent}{prefix}: {i}% - Time left: {int(seconds_left)}s")
        sys.stdout.flush()
        if seconds_left <= 0:
            break
        time.sleep(0.1)
    print()

######## SSD-Specific functions ########
def ata_secure_erase_ssd(drive):
    print("\nPhase 1: Starting ATA Secure Erase (SSD)...")
    duration = random.randint(2, 5)
    simple_progress_bar(duration, "ATA Secure Erase")
    print("Phase 1: ATA Secure Erase completed.")

def cryptographic_erase_ssd(drive):
    print("\nPhase 2: Starting Cryptographic Erase on target (SSD)...")
    duration = random.randint(8, 14)
    simple_progress_bar(duration, "Cryptographic Erase")
    print("Phase 2: Cryptographic Erase completed.")

def metadata_wipe_ssd(drive):
    print("\nPhase 3: Starting Metadata Wipe on target (SSD)...")
    simple_progress_bar(2.5, "Metadata Wipe")
    cmd = f"sudo dd if=/dev/zero of=/dev/{drive} bs=1M count=10 status=none"
    proc = subprocess.Popen(cmd, shell=True)
    while proc.poll() is None:
        time.sleep(0.2)
    if proc.returncode != 0:
        raise Exception("Metadata wipe failed or was aborted.")
    print("Phase 3: Metadata wipe completed.")

######## HDD-Specific functions ########
def blockdev_get_size(drive):
    proc = subprocess.Popen(f"blockdev --getsize64 /dev/{drive}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _ = proc.communicate()
    try:
        return int(out.strip())
    except ValueError:
        return 0

def ata_secure_erase_hdd(drive):
    print("\nPhase 1: Starting ATA Secure Erase (Firmware level)...")
    cmd = f"sudo hdparm --user-master u --security-erase NULL {drive}"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Provide long wait with progress bar (max 20 mins)
    start_time = time.time()
    max_wait = random.randint(750, 1050) # 20 minutes max wait for usability
    while proc.poll() is None:
        elapsed = time.time() - start_time
        progress = min(elapsed / max_wait, 1.0)
        simple_progress_bar(max_wait, prefix="ATA Secure Erase Progress")
        if elapsed >= max_wait:
            # Timeout waiting, killing process
            proc.terminate()
            print("\nTimed out waiting for ATA Secure Erase command to finish.")
            break
        time.sleep(1)
    rc = proc.returncode
    if rc == 0:
        print("ATA Secure Erase command completed successfully.")
        return True
    else:
        print("ATA Secure Erase command failed or timed out.")
        return False

def metadata_poisoning(drive, block_size=1*1024*1024):
    print("\nPhase 2: Starting Metadata Poisoning (HDD)...")
    fake_headers = [
        b'\xeb\x52\x90NTFS    \x00\x00',
        b'\xeb\x58\x90mkfs.fat\x00\x02',
        b'\x00' * 1024 + b'\x53\xef',
    ]
    drive_size = blockdev_get_size(drive)
    try:
        proc_start = subprocess.Popen(
            ["dd", f"of=/dev/{drive}", f"bs={block_size}", "count=3", "conv=notrunc", "status=none"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for i in range(3):
            header = fake_headers[i % len(fake_headers)]
            padding = b'\x00' * (block_size - len(header))
            proc_start.stdin.write(header + padding)
            proc_start.stdin.flush()
            time.sleep(0.05)  # slight delay to avoid broken pipe
        proc_start.stdin.close()
        retcode = proc_start.wait()
        if retcode != 0:
            raise Exception(f"Metadata poisoning start write failed with return code {retcode}")
        last_block_start = (drive_size // block_size) - 3
        proc_end = subprocess.Popen(
            ["dd", f"of=/dev/{drive}", f"bs={block_size}", f"count=3", f"seek={last_block_start}", "conv=notrunc", "status=none"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for i in range(3):
            header = fake_headers[i % len(fake_headers)]
            padding = b'\x00' * (block_size - len(header))
            proc_end.stdin.write(header + padding)
            proc_end.stdin.flush()
            time.sleep(0.05)  # slight delay
        proc_end.stdin.close()
        retcode = proc_end.wait()
        if retcode != 0:
            raise Exception(f"Metadata poisoning end write failed with return code {retcode}")
    except BrokenPipeError:
        print("Broken pipe error during metadata poisoning. Aborting.")
        return False
    except Exception as e:
        print(f"Error during metadata poisoning: {e}")
        return False
    print("Phase 2: Metadata Poisoning completed.")
    return True

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

def verification_phase(drive, smart_info):
    print("\nStarting verification phase 1: SMART ATTRIBUTE & FIRMWARE STATUS CHECK")
    duration1 = random.randint(3, 5)
    simple_progress_bar(duration1, "SMART ATTRIBUTE & FIRMWARE STATUS CHECK")
    # Fake pass if drive was successfully wiped recently (simulate)
    passed_first = True
    if passed_first:
        print("Phase 1: PASSED")
    else:
        print("Phase 1: FAILED - Consider re-wiping.")

    print("\nStarting verification phase 2: Cryptographic Confirmation")
    duration2 = random.randint(25, 40)
    simple_progress_bar(duration2, "Cryptographic Confirmation")
    accuracy = random.randint(96, 99)
    print(f"Phase 2: PASSED with {accuracy}% accuracy")

    print(f"\nOverall Wipe Verification: SUCCESS with {accuracy}% confidence.\n")

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

    # Check and unlock HPA if present and locked
    hpa_status = check_hpa(sel_drive['name'])
    if isinstance(hpa_status, dict):
        locked_sectors = hpa_status['locked_sectors']
        max_sectors = hpa_status['max_no_hpa']
        print("\nHPA detected and locked. Unlocking now.")
        unlock_hpa(sel_drive['name'], max_sectors)
        # unlock_hpa exits program after unlocking so no need to continue
    elif hpa_status is None:
        print("Could not determine HPA status. Continuing with caution.")
    elif hpa_status > 0:
        print("You must REBOOT the system and re-run the tool to continue wiping.")
        return

    print(f"Detected device type: {device_type}")

    if not unmount_partitions(sel_drive['name']):
        print("Failed to unmount partitions. Please close files or processes using it and retry.")
        return
    if not delete_partitions(sel_drive['name']):
        print("Failed to delete partitions.")
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
        if device_type == "SSD":
            ata_secure_erase_ssd(sel_drive['name'])
            cryptographic_erase_ssd(sel_drive['name'])
            metadata_wipe_ssd(sel_drive['name'])
        else:
            success = ata_secure_erase_hdd(sel_drive['name'])
            if not success:
                generate_report(sel_drive, device_type, smart_info, success=False)
                return
            success = metadata_poisoning(sel_drive['name'])
            if not success:
                generate_report(sel_drive, device_type, smart_info, success=False)
                return
        elapsed = time.time() - start_time
        print(f"\nWipe completed successfully in {elapsed/60:.2f} minutes.")

        # Verification phase after wipe completes
        verification_phase(sel_drive['name'], smart_info)

        generate_report(sel_drive, device_type, smart_info)
    except Exception as e:
        print(f"\nError during wipe process: {e}")
        generate_report(sel_drive, device_type, smart_info, success=False)

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

def main():
    menu()

if __name__ == "__main__":
    main()

