#!/usr/bin/env python3
import subprocess
import sys
import time
import random
import hashlib



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
        time.sleep(0.1)  # refresh every 0.1 sec, so timer looks smooth
    print()


def ata_secure_erase(drive):
    print("\nStarting ATA Secure Erase (Firmware level)...")
    cmd = f"sudo hdparm --user-master u --security-erase NULL {drive}"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Provide long wait with progress bar (max 20 mins)
    start_time = time.time()
    max_wait = 1200 # 20 minutes max wait for usability
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


def main():
    drive = '/dev/sda'
    overall_start = time.time()

    print(f"WipeTech Pro starting advanced wipe on {drive}")

    # Step 1: ATA Secure Erase
    step_start = time.time()
    result = ata_secure_erase(drive)
    step_end = time.time()
    print(f"Step 1 completed in {(step_end - step_start)/60:.2f} mins\n")

    overall_end = time.time()
    print(f"Advanced wipe finished in {(overall_end - overall_start)/60:.2f} minutes.")


if __name__ == "__main__":
    main()

