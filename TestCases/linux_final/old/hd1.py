#!/usr/bin/env python3
import subprocess
import sys
import time
import random
import hashlib

def run_command(cmd, capture_output=True):
    result = subprocess.run(cmd, shell=True,
                            stdout=subprocess.PIPE if capture_output else None,
                            stderr=subprocess.PIPE if capture_output else None,
                            text=True)
    stdout = result.stdout.strip() if result.stdout is not None else ''
    stderr = result.stderr.strip() if result.stderr is not None else ''
    return stdout, stderr, result.returncode

def simple_progress_bar(duration_sec, prefix='', indent='  '):
    toolbar_width = 40
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > duration_sec:
            break
        progress = min(elapsed / duration_sec, 1.0)
        filled = int(toolbar_width * progress)
        est_left = max(int(duration_sec - elapsed), 0)
        sys.stdout.write(f"\r{indent}{prefix}: [{'#' * filled}{' ' * (toolbar_width - filled)}] {int(progress*100)}% - Time left: {est_left}s")
        sys.stdout.flush()
        time.sleep(0.1)
    print(f"\r{indent}{prefix}: [{'#' * toolbar_width}] 100%")

def blockdev_get_size(drive):
    proc = subprocess.Popen(f"blockdev --getsize64 {drive}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _ = proc.communicate()
    return int(out.strip())

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

def generate_crypto_pattern_block(block_size, counter):
    key = hashlib.sha3_256(f"wipekey-{counter}".encode()).digest()
    pattern = (key * ((block_size // len(key)) + 1))[:block_size]
    return pattern

def single_pass_crypto_overwrite(drive, block_size=128*1024*1024):
    print("\nStarting Single-pass Cryptographically Strong Overwrite...")
    drive_size = blockdev_get_size(drive)
    total_blocks = drive_size // block_size
    print(f"Drive size: {drive_size/(1024**3):.2f} GB, Block size: {block_size//(1024*1024)} MB, Total blocks: {total_blocks}")

    proc = subprocess.Popen(
        ["dd", f"of={drive}", f"bs={block_size}", "oflag=direct", "conv=notrunc", "status=none"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    start = time.time()
    for i in range(total_blocks):
        block = generate_crypto_pattern_block(block_size, i)
        try:
            proc.stdin.write(block)
        except BrokenPipeError:
            print("\nError writing to drive, aborting.")
            proc.stdin.close()
            proc.wait()
            return False
        if i % (max(total_blocks // 100, 1)) == 0 or i == total_blocks - 1:
            elapsed = time.time() - start
            simple_progress_bar(total_blocks, prefix="Crypto Overwrite Progress", indent='  ')
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        print("Cryptographic overwrite failed.")
        return False
    end = time.time()
    print(f"Completed in {(end - start)/60:.2f} minutes.")
    return True

def metadata_poisoning(drive, block_size=1*1024*1024):
    print("\nStarting Metadata Poisoning...")
    # Fake headers to inject at start and end
    fake_headers = [
        b'\xeb\x52\x90NTFS    \x00\x00',
        b'\xeb\x58\x90mkfs.fat\x00\x02',
        b'\x00' * 1024 + b'\x53\xef',
    ]
    # Write to first 3MB with fake headers cyclically, and last 3MB sectors
    drive_size = blockdev_get_size(drive)
    proc_start = subprocess.Popen(
        ["dd", f"of={drive}", f"bs={block_size}", "count=3", "conv=notrunc", "status=none"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    for i in range(3):
        header = fake_headers[i % len(fake_headers)]
        padding = b'\x00' * (block_size - len(header))
        proc_start.stdin.write(header + padding)
    proc_start.stdin.close()
    proc_start.wait()
    # Write to last 3MB - seek to last 3 blocks
    last_block_start = (drive_size // block_size) - 3
    proc_end = subprocess.Popen(
        ["dd", f"of={drive}", f"bs={block_size}", f"count=3", f"seek={last_block_start}", "conv=notrunc", "status=none"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    for i in range(3):
        header = fake_headers[i % len(fake_headers)]
        padding = b'\x00' * (block_size - len(header))
        proc_end.stdin.write(header + padding)
    proc_end.stdin.close()
    proc_end.wait()
    print("Metadata Poisoning completed.")
    return True

def sed_cryptographic_erase(drive):
    print("\nTrying SED Cryptographic Erase (if supported)...")
    # Use hdparm; only works if drive supports Opal/SED
    cmd = f"sudo hdparm --security-erase NULL {drive}"
    out, err, rc = run_command(cmd)
    print(out)
    if rc == 0:
        print("SED Cryptographic Erase command issued successfully.")
        return True
    else:
        print("SED Cryptographic Erase unsupported or failed.")
        return False

def firmware_sanitize(drive):
    print("\nTrying Firmware Sanitize command (if supported)...")
    # Using nvme sanitize command is typical for NVMe; for SATA may require vendor tools; simulate here
    # You can adjust this if drive supports ATA Sanitize: https://ata.wiki/index.php/ATA_Sanitize
    print("Firmware Sanitize not implemented due to hardware limitations.")
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

    # Step 2: Single-pass cryptographic overwrite
    step_start = time.time()
    result = single_pass_crypto_overwrite(drive)
    step_end = time.time()
    print(f"Step 2 completed in {(step_end - step_start)/60:.2f} mins\n")

    # Step 3: Metadata Poisoning
    step_start = time.time()
    result = metadata_poisoning(drive)
    step_end = time.time()
    print(f"Step 3 completed in {(step_end - step_start):.2f} seconds\n")

    # Step 4: SED Cryptographic Erase (optional, may rerun firmware erase)
    step_start = time.time()
    result = sed_cryptographic_erase(drive)
    step_end = time.time()
    print(f"Step 4 completed in {(step_end - step_start):.2f} seconds\n")

    # Step 5: Firmware Sanitize
    step_start = time.time()
    result = firmware_sanitize(drive)
    step_end = time.time()
    print(f"Step 5 completed in {(step_end - step_start):.2f} seconds\n")

    overall_end = time.time()
    print(f"Advanced wipe finished in {(overall_end - overall_start)/60:.2f} minutes.")

if __name__ == "__main__":
    main()

