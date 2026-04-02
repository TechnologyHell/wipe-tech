import tkinter as tk
from tkinter import messagebox, ttk
import threading
import time
import os
import ctypes
from ctypes import wintypes
import subprocess

# -----------------------------
# Windows constants
# -----------------------------
GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
IOCTL_DISK_GET_LENGTH_INFO = 0x7405C

class GET_LENGTH(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ulonglong)]

# -----------------------------
# Drive helpers
# -----------------------------
def get_drive_size(drive_number: int) -> int:
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
    drives = []
    try:
        cmd = "Get-Disk | Select-Object Number, FriendlyName, Size | ConvertTo-Json"
        result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, check=True)
        disks = eval(result.stdout)
        if isinstance(disks, dict):
            disks = [disks]
        for d in disks:
            num = int(d["Number"])
            model = d["FriendlyName"]
            size_gb = int(d["Size"]) / (1024**3)
            drives.append((num, model, size_gb))
    except:
        pass
    return drives

# -----------------------------
# Wipe logic
# -----------------------------
def run_diskpart_clean(drive_number: int):
    commands = f"""
select disk {drive_number}
clean
create partition primary
assign letter=Z
"""
    subprocess.run(["diskpart"], input=commands, text=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def overwrite_drive_zeros(drive_number: int, chunk_mb=4):
    drive_path = f"\\\\.\\PhysicalDrive{drive_number}"
    handle = ctypes.windll.kernel32.CreateFileW(
        drive_path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
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

def wipe_drive_thread(drive_number, progress_var):
    t1 = threading.Thread(target=run_diskpart_clean, args=(drive_number,))
    t2 = threading.Thread(target=overwrite_drive_zeros, args=(drive_number,))
    t1.start()
    t2.start()
    # Simulate frontend progress for ~20 minutes
    size_gb = get_drive_size(drive_number) / (1024**3)
    duration = 20*60
    steps = 100
    for i in range(steps+1):
        percent = int(i/steps*100)
        progress_var.set(percent)
        time.sleep(duration/steps)
    t1.join()
    t2.join()
    messagebox.showinfo("WipeTech Pro", f"Drive {drive_number} wipe completed.")

# -----------------------------
# GUI
# -----------------------------
def main_gui():
    root = tk.Tk()
    root.title("WipeTech Pro")

    drives = list_drives()
    drive_options = [f"PhysicalDrive{d[0]} - {d[1]} - {d[2]:.1f} GB" for d in drives]
    drive_var = tk.StringVar()
    drive_var.set(drive_options[0] if drive_options else "")

    tk.Label(root, text="Select Drive to Wipe:").pack(pady=5)
    tk.OptionMenu(root, drive_var, *drive_options).pack(pady=5)

    progress_var = tk.IntVar()
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100, length=400)
    progress_bar.pack(pady=20)

    def start_wipe():
        selection = drive_var.get()
        if not selection:
            messagebox.showwarning("WipeTech Pro", "No drive selected!")
            return
        drive_number = int(selection.split()[0].replace("PhysicalDrive",""))
        confirm = messagebox.askyesno("WipeTech Pro", f"Are you sure you want to wipe {selection}?")
        if confirm:
            threading.Thread(target=wipe_drive_thread, args=(drive_number, progress_var)).start()

    tk.Button(root, text="Start Wipe", command=start_wipe).pack(pady=10)
    tk.Button(root, text="Exit", command=root.destroy).pack(pady=5)

    root.mainloop()

if __name__ == "__main__":
    main_gui()
