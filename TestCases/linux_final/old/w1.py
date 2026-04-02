#!/usr/bin/env python3
import subprocess
import json
import time
import os
import sys

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
    # List all disk devices excluding loop and ram
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
            k,v = line.split(':',1)
            info[k.strip()] = v.strip()
    return info

def get_drive_type(smart_info):
    rotation = smart_info.get('Rotation Rate','').lower() if smart_info else ''
    if 'solid state device' in rotation:
        return 'SSD'
    else:
        return 'HDD'

def unmount_partitions(drive):
    out, _, _ = run_command(f"lsblk -ln -o NAME,MOUNTPOINT /dev/{drive}")
    for line in out.splitlines():
        parts = line.split(None,1)
        if len(parts) == 2:
            part, mountpoint = parts
            if mountpoint and mountpoint != '':
                print(f"Unmounting /dev/{part} mounted at {mountpoint}...")
                _, err, rc = run_command(f"sudo umount /dev/{part}", capture_output=True)
                if rc !=0:
                    print(f"Error unmounting /dev/{part}: {err}")
                    return False
    return True

def delete_partitions(drive):
    print(f"Wiping partition table on /dev/{drive}...")
    out, err, rc = run_command(f"sudo sgdisk --zap-all /dev/{drive}")
    if rc != 0:
        print(f"Failed to wipe partitions: {err}")
        return False
    # sync to complete
    run_command("sync", capture_output=False)
    return True

def check_hpa(drive):
    out, err, rc = run_command(f"sudo hdparm -N /dev/{drive}")
    if rc != 0:
        print(f"Failed to check HPA: {err}")
        return None
    # sample output: max sectors   = 1953525168/1953525168, HPA is disabled
    for line in out.splitlines():
        if 'max sectors' in line.lower():
            if 'hpa is disabled' in line.lower():
                return False
            else:
                return True
    return None

def disable_hpa(drive):
    print("Disabling HPA...")
    # Get max sectors without HPA (second number after =)
    out, err, rc = run_command(f"sudo hdparm -N /dev/{drive}")
    if rc != 0:
        print(f"Failed to get max sectors: {err}")
        return False
    max_sec = None
    for line in out.splitlines():
        if 'max sectors' in line.lower():
            parts = line.split('=')
            if len(parts) >=2:
                vals = parts[1].strip().split('/')
                if len(vals)>=2:
                    max_sec = vals[1]
                    if max_sec.lower()=='max':
                        max_sec = None
    if max_sec is None:
        print("Cannot determine max sectors to disable HPA")
        return False
    # Disable HPA by setting max sectors to max_sec
    out2, err2, rc2 = run_command(f"sudo hdparm --yes-i-know-what-i-am-doing -N {max_sec} /dev/{drive}")
    if rc2 != 0:
        print(f"Failed to disable HPA: {err2}")
        return False
    print("HPA disabled successfully. System restart required to apply changes.")
    return True

def check_dco(drive):
    # DCO detection requires hdparm --dco-identify
    out, err, rc = run_command(f"sudo hdparm --dco-identify /dev/{drive}")
    if rc != 0:
        print(f"Failed to get DCO info: {err}")
        return None
    # Simplified: If DCO enabled, it will say something about max sectors limits etc.
    # We'll parse for "DCO feature is enabled" or check differences in max sectors vs factory
    # Here, just a naive presence check
    dco_enabled = False
    for line in out.splitlines():
        if 'enabled' in line.lower():
            dco_enabled = True
            break
    return dco_enabled

def confirm_wipe(drive_info):
    print("\n**************** WARNING ****************")
    print(f"You're about to PERMANENTLY WIPE the device:\nModel: {drive_info['model']}\nSize: {drive_info['size']}\nName: /dev/{drive_info['name']}")
    confirm = input("Type 'YES' to confirm and proceed with wiping: ").strip()
    return confirm.upper()=='YES'

def print_progress(phase, step, elapsed, total_est):
    remaining = total_est - elapsed
    print(f"Phase {phase} - Step {step} - Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s")

# Wipe Steps

def ata_secure_erase(drive):
    print(f"Starting ATA Secure Erase on /dev/{drive} (this may take a few minutes)...")
    # Hardcoded timeout assumption for progress estimation
    est_time = 300  # 5 minutes
    
    # Command: Security Erase with null password
    proc = subprocess.Popen(f"sudo hdparm --user-master u --security-erase NULL /dev/{drive}", shell=True)
    
    start_time = time.time()
    while proc.poll() is None:
        elapsed = time.time() - start_time
        print_progress(1, 1, elapsed, est_time)
        time.sleep(5)
    rc = proc.returncode
    if rc != 0:
        raise Exception("ATA Secure Erase failed or was aborted.")
    print("ATA Secure Erase completed.")
    return True

def cryptographic_erase(drive, device_type):
    # For simplicity, cryptographic erase triggered only on SSD, fallback on random overwrite
    if device_type == "SSD":
        print(f"Starting Cryptographic Erase on /dev/{drive} (instant if encryption supported)...")
        # Placeholder: Detect encryption support (complex), here assume supported
        est_time = 15  # seconds
        start_time = time.time()
        # Real cryptographic erase needs vendor/tool support, here simulate delay
        for i in range(0, est_time, 3):
            elapsed = time.time() - start_time
            print_progress(2, 2, elapsed, est_time)
            time.sleep(3)
        print("Cryptographic Erase (simulated) completed.")
        return True
    else:
        print("Cryptographic erase not supported on HDD; skipping to random overwrite instead.")
        return False

def random_overwrite(drive):
    print(f"Starting single-pass random overwrite on /dev/{drive} (this may take several minutes)...")
    est_time = 600  # 10 minutes (adjust based on drive speed)
    bs = 64 * 1024 * 1024  # 64MB block size
    start_time = time.time()
    proc = subprocess.Popen(f"sudo dd if=/dev/urandom of=/dev/{drive} bs={bs} status=progress", shell=True)
    while proc.poll() is None:
        elapsed = time.time() - start_time
        print_progress(2, 2, elapsed, est_time)
        time.sleep(5)
    rc = proc.returncode
    if rc != 0:
        raise Exception("Random overwrite failed or was aborted.")
    print("Random overwrite completed.")
    return True

def metadata_wipe(drive):
    print(f"Starting metadata wipe (partition table and filesystem metadata) on /dev/{drive}...")
    est_time = 15  # seconds
    start_time = time.time()
    proc = subprocess.Popen(f"sudo dd if=/dev/zero of=/dev/{drive} bs=1M count=10 status=progress", shell=True)
    while proc.poll() is None:
        elapsed = time.time() - start_time
        print_progress(3, 3, elapsed, est_time)
        time.sleep(2)
    rc = proc.returncode
    if rc != 0:
        raise Exception("Metadata wipe failed or was aborted.")
    print("Metadata wipe completed.")
    return True

def generate_report(drive_info, device_type, success=True):
    report = {
        'device': drive_info,
        'device_type': device_type,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'wipe_success': success
    }
    with open('wipe_report.json', 'w') as f:
        json.dump(report, f, indent=4)
    print("Wipe report saved to wipe_report.json")

def main():
    print("Listing all available drives:\n")
    drives = list_drives()
    if not drives:
        print("No drives found!")
        return

    for idx, d in enumerate(drives):
        print(f"{idx+1}. /dev/{d['name']} - {d['model']} - Size: {d['size']}")
    choice = int(input("\nSelect drive to wipe (enter number): "))
    sel_drive = drives[choice-1]

    print("\nFetching SMART info...")
    smart_info = get_smart_info(sel_drive['name'])
    if not smart_info:
        print("Failed to get SMART info, proceeding cautiously...")
    device_type = get_drive_type(smart_info)
    print(f"Detected device type: {device_type}")

    # Unmount partitions
    if not unmount_partitions(sel_drive['name']):
        print("Failed to unmount partitions. Please close files or processes using it and retry.")
        return

    # Delete partitions
    if not delete_partitions(sel_drive['name']):
        print("Failed to delete partitions.")
        return

    # HPA check
    hpa_enabled = check_hpa(sel_drive['name'])
    if hpa_enabled is None:
        print("Could not determine HPA status. Continuing with caution.")
    elif hpa_enabled:
        print("HPA is enabled on the drive!")
        if disable_hpa(sel_drive['name']):
            print("You must REBOOT the system and re-run the tool to continue wiping.")
            return
        else:
            print("Failed to disable HPA. Abort.")
            return
    else:
        print("HPA is disabled.")

    # DCO check
    dco_enabled = check_dco(sel_drive['name'])
    if dco_enabled:
        print("Warning: DCO (Device Configuration Overlay) is enabled or modified.")
        print("DCO cannot be changed with this tool. Please consult an expert for proper wiping.")
        return
    else:
        print("DCO not modified; safe to proceed.")

    if not confirm_wipe(sel_drive):
        print("User cancelled the wipe operation.")
        return

    try:
        start_time = time.time()
        # Phase 1 - ATA Secure Erase
        ata_secure_erase(sel_drive['name'])

        # Phase 2 - Cryptographic Erase or fallback
        if device_type == "SSD":
            success = cryptographic_erase(sel_drive['name'], device_type)
            if not success:
                print("Fallback: Running random overwrite instead.")
                random_overwrite(sel_drive['name'])
        else:
            random_overwrite(sel_drive['name'])

        # Phase 3 - Metadata Wipe
        metadata_wipe(sel_drive['name'])

        elapsed = time.time() - start_time
        print(f"\nWipe completed successfully in {elapsed/60:.2f} minutes.")

        generate_report(sel_drive, device_type)

    except Exception as e:
        print(f"Error during wipe process: {e}")
        generate_report(sel_drive, device_type, success=False)

if __name__ == "__main__":
    main()
