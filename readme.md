# WipeTech Pro - Secure Data Erasure Tool

### **Solving the Problem of Unsecure Data Deletion**

**WipeTech Pro** is a robust, cross-platform data-wiping solution developed during **Smart India Hackathon (SIH) 2025**. It addresses the critical security flaw of "soft deletion," where sensitive data remains recoverable on discarded electronic storage media.

Conventional formatting or deletion merely removes the file pointers, leaving the actual data intact on the disk. WipeTech Pro ensures that data is permanently and irrecoverably erased using advanced multi-phase wiping techniques.

-----

## 📺 Demo Video

Check out the tool in action. This demo was submitted for the final round of SIH 2025:
https://youtu.be/WV3siNaGdW4

-----

## 🛡️ Key Features

  - **Multi-Phase Wiping**: Combines three powerful techniques to ensure zero data recovery:
    1.  **Secure ATA Erase**: Utilizes the drive's built-in firmware commands for a hardware-level wipe.
    2.  **Cryptographic Randomization**: Overwrites the entire storage with random bits to break any remaining data patterns.
    3.  **Metadata Poisoning**: Specifically targets and corrupts the file system metadata (MFT/Inodes).
  - **Cross-Platform Support**: Fully functional on **Windows** (PowerShell/GUI) and **Linux** (Ubuntu/Terminal).
  - **Non-Tamperable Certification**: Generates a secure PDF certificate and a JSON log upon successful completion, featuring a unique hash for verification.
  - **HPA & DCO Detection**: Identifies hidden sectors like Host Protected Areas (HPA) to ensure no data is left in "hidden" drive segments.
  - **User-Friendly Interface**: Simple GUI to select drives and monitor the wiping process in real-time.

-----

## 🚀 How It Works

1.  **Drive Selection**: The tool lists all connected physical drives (HDDs, SSDs, USBs).
2.  **Pre-Checks**: It performs SMART attribute checks and looks for HPA/DCO status.
3.  **Wiping Sequence**: Executes the 3-phase wipe, typically completing a standard SSD wipe in under a minute via firmware integration.
4.  **Verification**: Compares post-wipe metadata against previous states to confirm success.
5.  **Certification**: Issues a signed certificate containing the drive model, serial number, and wipe timestamp.

-----

## 📂 Project Structure

  - `/windows`: Source code for the Windows PowerShell-based GUI and logic.
  - `/linux`: Python-based implementation for Linux distributions.
  - `/docs`: Documentation and technical specifications for the 3-phase algorithm.

-----

## 🛠️ Installation & Usage

### Windows

1.  Open PowerShell as Administrator.
2.  Navigate to the project directory.
3.  Run the tool:
    ```powershell
    python wipe_gui.ps1
    ```

### Linux

1.  Grant execution permissions:
    ```bash
    sudo chmod +x wipetech_gui.py
    ```
2.  Run with root privileges:
    ```bash
    sudo python3 wipetech_gui.py
    ```

-----

## 🏆 SIH 2025 Achievement

This project was developed for **Problem Statement ID: 25070** (Secure Data Wiping for Trustworthy IT Asset Recycling) under the **Ministry of Mines**. It aims to promote a circular economy by making the disposal of electronic waste safe and secure for individuals and organizations alike.
This project stood as winner under the Internal Hackathon for SIH 2026

-----

### **Team: TechZeno**

*Lead Developer: Nitish Singh* ; 
*Assisting Developer: Sweta Kumari*

-----

*Disclaimer: This tool is designed for permanent data destruction. Please use with caution, as data erased using WipeTech Pro cannot be recovered by any known means.*
