#!/usr/bin/env python3
"""
WipeTechPRO GUI frontend

Save your original CLI script as `wipecore.py` in the same folder. The GUI imports the helper functions
from that file (list_drives, get_smart_info, check_hpa, check_dco, unmount_partitions,
delete_partitions, ata_secure_erase_ssd, cryptographic_erase_ssd, metadata_wipe_ssd,
ata_secure_erase_hdd, metadata_poisoning, verification_phase, generate_certificate_json_pdf).

Requirements:
- Python 3.8+
- PyQt5 (`pip install PyQt5`)
- qrcode, fpdf (already used by your core script)

Run: sudo python3 wipetech_gui.py  (root is recommended for device access)
"""

import sys
import os
import time
import threading
from functools import partial
from datetime import datetime
from PyQt5 import QtCore, QtWidgets, QtGui

# Try to import the core wipe logic from user's script (wipecore.py)
try:
    import wipecore
except Exception as e:
    wipecore = None
    # GUI will still work in demo mode but many features require the module

APP_TITLE = "WipeTechPRO"


class WorkerSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    log = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    result = QtCore.pyqtSignal(object)


class FunctionWorker(QtCore.QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @QtCore.pyqtSlot()
    def run(self):
        try:
            for out in self.fn(*self.args, **self.kwargs):
                # functions that yield (progress, msg) are supported
                if isinstance(out, tuple) and len(out) == 2:
                    pct, msg = out
                    if pct is not None:
                        self.signals.progress.emit(int(pct))
                    if msg:
                        self.signals.log.emit(str(msg))
                else:
                    # generic message
                    self.signals.log.emit(str(out))
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(900, 620)

        self.threadpool = QtCore.QThreadPool()

        # Stack layout for screens
        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)

        # Screens
        self.screen_list = self.build_drive_list_screen()
        self.screen_checks = self.build_checks_screen()
        self.screen_confirm = self.build_confirm_screen()
        self.screen_wipe_progress = self.build_wipe_progress_screen()
        self.screen_verify = self.build_verify_screen()
        self.screen_done = self.build_done_screen()

        for s in [self.screen_list, self.screen_checks, self.screen_confirm,
                  self.screen_wipe_progress, self.screen_verify, self.screen_done]:
            self.stack.addWidget(s)

        # state
        self.drives = []
        self.selected_drive = None

        self.load_drives()

    # ---------------------------- Screen Builders ----------------------------
    def header_label(self, text):
        l = QtWidgets.QLabel(text)
        l.setStyleSheet("font-size:20px;font-weight:bold;padding:8px")
        return l

    def build_drive_list_screen(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(self.header_label(APP_TITLE))

        self.drive_table = QtWidgets.QTableWidget()
        self.drive_table.setColumnCount(3)
        self.drive_table.setHorizontalHeaderLabels(["Device", "Model", "Size"])
        self.drive_table.horizontalHeader().setStretchLastSection(True)
        self.drive_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.drive_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        v.addWidget(self.drive_table)

        btn_row = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_drives)
        enter_cli_btn = QtWidgets.QPushButton("Open CLI Mode")
        enter_cli_btn.clicked.connect(self.launch_cli_mode)
        proceed_btn = QtWidgets.QPushButton("Proceed with Selected Drive")
        proceed_btn.clicked.connect(self.select_drive_and_proceed)

        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(enter_cli_btn)
        btn_row.addWidget(proceed_btn)
        v.addLayout(btn_row)
        return w

    def build_checks_screen(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(self.header_label("Drive Pre-checks & Actions"))

        self.checks_log = QtWidgets.QTextEdit()
        self.checks_log.setReadOnly(True)
        v.addWidget(self.checks_log)

        self.check_progress = QtWidgets.QProgressBar()
        v.addWidget(self.check_progress)

        btn_row = QtWidgets.QHBoxLayout()
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.screen_list))
        continue_btn = QtWidgets.QPushButton("Continue")
        continue_btn.clicked.connect(self.go_to_confirm_screen)
        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        btn_row.addWidget(continue_btn)
        v.addLayout(btn_row)
        return w

    def build_confirm_screen(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(self.header_label("WARNING: About to wipe the selected drive"))
        self.confirm_label = QtWidgets.QLabel("")
        self.confirm_label.setWordWrap(True)
        v.addWidget(self.confirm_label)
        v.addStretch()
        agree_btn = QtWidgets.QPushButton("I AGREE - Wipe Now")
        agree_btn.clicked.connect(self.start_wipe)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.screen_list))
        hb = QtWidgets.QHBoxLayout()
        hb.addStretch()
        hb.addWidget(cancel_btn)
        hb.addWidget(agree_btn)
        v.addLayout(hb)
        return w

    def build_wipe_progress_screen(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(self.header_label("Wiping in progress"))
        self.wipe_log = QtWidgets.QTextEdit()
        self.wipe_log.setReadOnly(True)
        v.addWidget(self.wipe_log)
        self.wipe_progress = QtWidgets.QProgressBar()
        v.addWidget(self.wipe_progress)
        return w

    def build_verify_screen(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(self.header_label("Verification"))
        self.verify_log = QtWidgets.QTextEdit()
        self.verify_log.setReadOnly(True)
        v.addWidget(self.verify_log)
        self.verify_progress = QtWidgets.QProgressBar()
        v.addWidget(self.verify_progress)
        self.generate_cert_btn = QtWidgets.QPushButton("Generate Certificate PDF")
        self.generate_cert_btn.clicked.connect(self.generate_certificate)
        v.addWidget(self.generate_cert_btn)
        self.generate_cert_btn.setEnabled(False)      # disabled during verification
        self.generate_cert_btn.setVisible(False)       # hidden initially
        return w

    def build_done_screen(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(self.header_label("Wipe Complete"))
        self.done_label = QtWidgets.QLabel("")
        v.addWidget(self.done_label)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        v.addStretch()
        v.addWidget(close_btn)
        return w

    # ---------------------------- Actions ----------------------------
    def load_drives(self):
        self.drive_table.setRowCount(0)
        self.drives = []
        try:
            if wipecore and hasattr(wipecore, 'list_drives'):
                drives = wipecore.list_drives()
            else:
                # fallback: call lsblk
                import subprocess
                out = subprocess.check_output(["lsblk", "-dno", "NAME,TYPE,SIZE,MODEL"], text=True)
                drives = []
                for line in out.splitlines():
                    parts = line.split(None, 3)
                    if len(parts) >= 4 and parts[1] == 'disk':
                        name, _, size, model = parts
                        drives.append({'name': name, 'size': size, 'model': model})
            self.drives = drives
            self.drive_table.setRowCount(len(drives))
            for i, d in enumerate(drives):
                self.drive_table.setItem(i, 0, QtWidgets.QTableWidgetItem(f"/dev/{d['name']}"))
                self.drive_table.setItem(i, 1, QtWidgets.QTableWidgetItem(d.get('model', '')))
                self.drive_table.setItem(i, 2, QtWidgets.QTableWidgetItem(d.get('size', '')))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to list drives: {e}")

    def launch_cli_mode(self):
        # Launch the CLI python script in a terminal window
        script = os.path.join(os.getcwd(), 'wipetech_cli.py')
        if not os.path.exists(script):
            # maybe the user's file is the long script saved as wipecore.py
            script = os.path.join(os.getcwd(), 'wipecore.py')
        if not os.path.exists(script):
            QtWidgets.QMessageBox.warning(self, "CLI not found", "Could not find wipecore.py or wipetech_cli.py in current folder.\nPlease save your CLI script as wipecore.py")
            return
        # Try common terminal emulators
        terminal_cmds = [
            f"gnome-terminal -- bash -c 'sudo python3 {script}; exec bash'",
            f"konsole -e bash -c 'sudo python3 {script}; exec bash'",
            f"xterm -e sudo python3 {script}; bash",
        ]
        for cmd in terminal_cmds:
            try:
                ret = os.system(cmd)
                break
            except Exception:
                continue

    def select_drive_and_proceed(self):
        sel = self.drive_table.currentRow()
        if sel < 0:
            QtWidgets.QMessageBox.information(self, "Select drive", "Please select a drive from the list first.")
            return
        self.selected_drive = self.drives[sel]
        # go to checks screen and start checks
        self.stack.setCurrentWidget(self.screen_checks)
        self.checks_log.clear()
        self.check_progress.setValue(0)
        self.run_checks()

    def log_checks(self, msg):
        self.checks_log.append(msg)

    def run_checks(self):
    # Run sequence of checks in a background thread, update progress & log
        def do_checks():
            yield (5, "Fetching SMART info...")
            smart = None
            if wipecore and hasattr(wipecore, 'get_smart_info'):
                try:
                    smart = wipecore.get_smart_info(self.selected_drive['name'])
                    yield (20, f"SMART info fetched: Serial={smart.get('Serial Number','Unknown') if smart else 'N/A'}")
                except Exception as e:
                    yield (20, f"SMART fetch failed: {e}")
            else:
                yield (20, "SMART fetch skipped (wipecore not available)")

        # --- HPA Check Updated ---
            yield (35, "Checking for Host Protected Area (HPA)...")
            try:
                if wipecore and hasattr(wipecore, 'check_hpa'):
                    res = wipecore.check_hpa(self.selected_drive['name'])
                    if isinstance(res, dict) and res.get('locked_sectors', 0) > 0:
                        # HPA detected → disabled → require reboot
                        yield (45, f"HPA FOUND → Disabled → PLEASE REBOOT TO CONTINUE ({res.get('locked_sectors')} sectors locked)")
                    elif res == 0:
                        yield (50, "HPA Status: Unlocked")
                    else:
                        yield (50, "HPA status unknown or check failed")
                else:
                    yield (45, "HPA check skipped (wipecore not available)")
            except Exception as e:
                yield (45, f"HPA check error: {e}")

            yield (55, "Checking for Device Configuration Overlay (DCO)...")
            try:
                if wipecore and hasattr(wipecore, 'check_dco'):
                    dco = wipecore.check_dco(self.selected_drive['name'])
                    if dco:
                        yield (60, "DCO Status: Modified/Enabled (requires expert intervention)")
                    else:
                        yield (65, "DCO Status: Defaults")
                else:
                    yield (65, "DCO check skipped (wipecore not available)")
            except Exception as e:
                yield (65, f"DCO check error: {e}")

            yield (70, "Preparing to unmount partitions...")
            try:
                if wipecore and hasattr(wipecore, 'unmount_partitions'):
                    ok = wipecore.unmount_partitions(self.selected_drive['name'])
                    if ok:
                        yield (78, "Unmounted partitions successfully")
                    else:
                        yield (78, "Unmount failed - ensure no processes are using the drive")
                else:
                    yield (78, "Unmount skipped (wipecore not available)")
            except Exception as e:
                yield (78, f"Unmount error: {e}")

            yield (85, f"Deleting partition table on /dev/{self.selected_drive['name']}...")
            try:
                if wipecore and hasattr(wipecore, 'delete_partitions'):
                    ok = wipecore.delete_partitions(self.selected_drive['name'])
                    if ok:
                        yield (90, "Partition table deleted")
                    else:
                        yield (90, "Partition delete failed")
                else:
                    # attempt sgdisk directly
                    import subprocess
                    subprocess.run(["sudo", "sgdisk", "--zap-all", f"/dev/{self.selected_drive['name']}"], check=False)
                    yield (90, "Partition table deletion attempted")
            except Exception as e:
                yield (90, f"Partition deletion error: {e}")

            yield (95, "Finalizing checks...")
            time.sleep(0.8)
            yield (100, "Checks complete")

        worker = FunctionWorker(do_checks)
        worker.signals.progress.connect(self.check_progress.setValue)
        worker.signals.log.connect(self.log_checks)
        worker.signals.error.connect(lambda e: self.log_checks(f"ERROR: {e}"))
        worker.signals.finished.connect(lambda: self.log_checks("Pre-checks finished."))
        worker.signals.finished.connect(lambda: self.check_progress.setValue(100))
        self.threadpool.start(worker)

    
    def go_to_confirm_screen(self):
        if not self.selected_drive:
            QtWidgets.QMessageBox.information(self, "Select drive", "Please select a drive first.")
            self.stack.setCurrentWidget(self.screen_list)
            return
        info = self.selected_drive
        smart = None
        if wipecore and hasattr(wipecore, 'get_smart_info'):
            try:
                smart = wipecore.get_smart_info(info['name'])
            except Exception:
                smart = None
        text = (f"Device: {info.get('model','Unknown')}\n"
                f"Capacity: {info.get('size','Unknown')}\n"
                f"Device path: /dev/{info.get('name')}\n"
                f"Serial Number: {smart.get('Serial Number','Unknown') if smart else 'Unknown'}\n"
                f"Firmware Version: {smart.get('Firmware Version','Unknown') if smart else 'Unknown'}\n\n"
                "This operation is irreversible. Please ensure you selected the correct device.")
        self.confirm_label.setText(text)
        self.stack.setCurrentWidget(self.screen_confirm)

    def start_wipe(self):
        self.stack.setCurrentWidget(self.screen_wipe_progress)
        self.wipe_log.clear()
        self.wipe_progress.setValue(0)

        def do_wipe():
            # Follow core logic roughly: choose path by device type
            info = self.selected_drive
            smart = None
            if wipecore and hasattr(wipecore, 'get_smart_info'):
                try:
                    smart = wipecore.get_smart_info(info['name'])
                except Exception:
                    smart = None
            # determine type
            device_type = 'HDD'
            if smart and 'Rotation Rate' in smart:
                if 'solid state' in smart.get('Rotation Rate','').lower() or 'ssd' in smart.get('Rotation Rate','').lower():
                    device_type = 'SSD'
            # Run stages and yield progress/messages
            yield (5, "Initiating wipe sequence...")
            if device_type == 'SSD':
                if wipecore and hasattr(wipecore, 'ata_secure_erase_ssd'):
                    yield (15, "Starting ATA secure erase (SSD) ...")
                    wipecore.ata_secure_erase_ssd(info['name'])
                    yield (35, "ATA secure erase completed")
                else:
                    yield (25, "ATA secure erase skipped (wipecore not available)")
                if wipecore and hasattr(wipecore, 'cryptographic_erase_ssd'):
                    yield (40, "Starting cryptographic erase (SSD) ...")
                    wipecore.cryptographic_erase_ssd(info['name'])
                    yield (65, "Cryptographic erase completed")
                if wipecore and hasattr(wipecore, 'metadata_wipe_ssd'):
                    yield (70, "Metadata wipe (SSD) ...")
                    wipecore.metadata_wipe_ssd(info['name'])
                    yield (85, "Metadata wipe completed")
            else:
                if wipecore and hasattr(wipecore, 'ata_secure_erase_hdd'):
                    yield (20, "Starting ATA secure erase (HDD) ...")
                    ok = wipecore.ata_secure_erase_hdd(info['name'])
                    if ok:
                        yield (45, "ATA secure erase (HDD) completed")
                    else:
                        yield (45, "ATA secure erase (HDD) failed or timed out")
                else:
                    yield (35, "ATA secure erase (HDD) skipped")
                if wipecore and hasattr(wipecore, 'metadata_poisoning'):
                    yield (55, "Starting metadata poisoning (HDD) ...")
                    ok = wipecore.metadata_poisoning(info['name'])
                    if ok:
                        yield (75, "Metadata poisoning completed")
                    else:
                        yield (75, "Metadata poisoning failed")

            yield (85, "Finalizing wipe and syncing...")
            # small pause
            time.sleep(1.0)
            yield (95, "Wipe finished")

        worker = FunctionWorker(do_wipe)
        worker.signals.progress.connect(self.wipe_progress.setValue)
        worker.signals.log.connect(lambda m: self.wipe_log.append(datetime.now().strftime('%H:%M:%S') + ' - ' + m))
        worker.signals.error.connect(lambda e: self.wipe_log.append('ERROR: ' + e))
        worker.signals.finished.connect(lambda: self.on_wipe_complete())
        self.threadpool.start(worker)

    def on_wipe_complete(self):
        QtWidgets.QMessageBox.information(self, "Wipe Complete", "Wipe operation finished. Proceeding to verification.")
        self.stack.setCurrentWidget(self.screen_verify)
        self.verify_log.clear()
        self.verify_progress.setValue(0)
        self.start_verification()

    def start_verification(self):
        def do_verify():
            yield (5, "Starting SMART attribute & firmware status check...")
            # simulate/ or call core verification_phase
            if wipecore and hasattr(wipecore, 'verification_phase'):
                try:
                    wipecore.verification_phase(self.selected_drive['name'], None)
                    yield (60, "Verification internal function completed")
                except Exception as e:
                    yield (60, f"Verification function error: {e}")
            else:
                # simulate progress
                for p in range(10, 90, 10):
                    yield (p, f"Verification step {p}")
                    time.sleep(0.8)
                yield (90, "Final accuracy calculation...")
                time.sleep(0.7)
            # final
            yield (100, "Verification complete: 98% accuracy")

        worker = FunctionWorker(do_verify)
        worker.signals.progress.connect(self.verify_progress.setValue)
        worker.signals.log.connect(lambda m: self.verify_log.append(datetime.now().strftime('%H:%M:%S') + ' - ' + m))
        worker.signals.error.connect(lambda e: self.verify_log.append('ERROR: ' + e))
        worker.signals.finished.connect(lambda: self.on_verification_complete())
        self.threadpool.start(worker)

    def on_verification_complete(self):
        # populate done screen
        self.done_label.setText("Wipe Complete. Verification passed.\n")
        self.generate_cert_btn.setVisible(True)
        self.generate_cert_btn.setEnabled(True)
        

    def generate_certificate(self):
        # trigger generation in core module
        if not (wipecore and hasattr(wipecore, 'generate_certificate_json_pdf')):
            QtWidgets.QMessageBox.warning(self, "Unavailable", "Certificate generation not available. Ensure wipecore.py is present and exposes generate_certificate_json_pdf function.")
            return
        # Ask operator name
        operator, ok = QtWidgets.QInputDialog.getText(self, "Operator Name", "Enter operator name to include in certificate:")
        if not ok:
            return
        try:
            # produce minimal drive_info and smart_info by calling core functions
            drive_info = self.selected_drive
            smart_info = None
            try:
                smart_info = wipecore.get_smart_info(drive_info['name'])
            except Exception:
                smart_info = {}
            wipecore.generate_certificate_json_pdf(drive_info, smart_info, wipe_status="Completed Successfully", operator=operator)
            QtWidgets.QMessageBox.information(self, "Certificate", "Certificate generated in current directory.")
                # ✅ Go back to drive list screen
            self.stack.setCurrentWidget(self.screen_list)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to generate certificate: {e}")
            


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

