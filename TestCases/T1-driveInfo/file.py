import subprocess
import re

def scan_drives():
    """Run smartctl --scan and parse available drives."""
    try:
        result = subprocess.run(["smartctl", "--scan"], capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split("\n")
        drives = []
        for line in lines:
            # Example: /dev/sda -d ata # /dev/sda, ATA device
            match = re.match(r"(/dev/\S+)\s+-d\s+(\S+)", line)
            if match:
                dev_path, iface = match.groups()
                drives.append({"path": dev_path, "interface": iface.upper()})
        return drives
    except subprocess.CalledProcessError as e:
        print("Error scanning drives:", e)
        return []

def get_drive_info(dev_path, iface):
    """Fetch drive info using smartctl -i"""
    cmd = ["smartctl", "-i", dev_path]
    if iface == "SAT":
        cmd.insert(2, "-d")
        cmd.insert(3, "sat")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout

        if "Error=5" in output:
            return {
                "model": "Access Denied",
                "size": "Access Denied",
                "serial": "Access Denied",
                "interface": iface
            }

        # Parse model
        model = re.search(r"(Device Model|Model Number|Model Family):\s+(.+)", output)
        model = model.group(2).strip() if model else "Unknown"

        # Parse capacity/size
        size = re.search(r"(User Capacity|Total NVM Capacity|Namespace 1 Size/Capacity):\s+(.+)", output)
        size = size.group(2).strip() if size else "Unknown"

        # Parse serial number
        serial = re.search(r"(Serial Number):\s+(.+)", output)
        serial = serial.group(2).strip() if serial else "Unknown"

        return {
            "model": model,
            "size": size,
            "serial": serial,
            "interface": iface
        }

    except Exception as e:
        return {
            "model": "Error",
            "size": "Error",
            "serial": "Error",
            "interface": iface
        }

def list_drives():
    drives = scan_drives()
    drive_info_list = []

    for i, drv in enumerate(drives, 1):
        info = get_drive_info(drv["path"], drv["interface"])
        drive_info_list.append(info)
        print(f"{i}. {drv['path']} | {info['model']} | {info['size']} | SN: {info['serial']} | Interface: {info['interface']}")
    
    if not drives:
        print("No drives detected.")
        return None

    # Let user select a drive
    selection = input("\nSelect a device number for further action (or press Enter to cancel): ")
    if selection.isdigit() and 1 <= int(selection) <= len(drives):
        chosen = drives[int(selection)-1]
        print(f"You selected {chosen['path']}")
        return chosen
    return None

def main():
    while True:
        print("\n--- Drive Wiper CLI ---")
        print("1. List all devices")
        print("2. Exit")
        choice = input("Enter choice: ").strip()

        if choice == "1":
            list_drives()
        elif choice == "2":
            print("Exiting...")
            break
        else:
            print("Invalid choice!")

if __name__ == "__main__":
    main()
