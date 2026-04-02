#!/usr/bin/env python3
import subprocess
import sys

FAKE_DEVICE = "/dev/sda"
FAKE_SIZE = "912G"
FAKE_MAX_SECTORS = "1780000000"
REAL_MAX_SECTORS = "1953525168"

# Define faked commands
def fake_hdparm(args):
    if "-N" in args and FAKE_DEVICE in args:
        print(f"{FAKE_DEVICE}:")
        print(f" max sectors   = {FAKE_MAX_SECTORS}/{REAL_MAX_SECTORS}, HPA is enabled")
        return 0
    else:
        return subprocess.run(["hdparm"] + args).returncode

def fake_lsblk(args):
    if FAKE_DEVICE in args:
        print("NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS")
        print(f"sda      8:0    0 {FAKE_SIZE}  0 disk")
    else:
        subprocess.run(["lsblk"] + args)

def main():
    # Replace system calls temporarily
    import builtins, os
    real_run = subprocess.run

    def run_wrapper(*args, **kwargs):
        cmd = args[0] if args else []
        if isinstance(cmd, list):
            if cmd[0] == "hdparm":
                return fake_hdparm(cmd[1:])
            elif cmd[0] == "lsblk":
                return fake_lsblk(cmd[1:])
        return real_run(*args, **kwargs)

    subprocess.run = run_wrapper
    os.system = lambda cmd: run_wrapper(cmd.split())

    # Launch your GUI tool in same process
    gui_script = "./wipetech_gui.py"  # path to your GUI
    with open(gui_script) as f:
        code = compile(f.read(), gui_script, 'exec')
        exec(code, {"__name__": "__main__"})

if __name__ == "__main__":
    main()

