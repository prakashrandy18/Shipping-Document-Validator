# 📦 Shipping Document Validator

A simple desktop application to compare shipping details between two PDF documents.

![Python](https://img.shields.io/badge/Python-3.7%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Mac%20%7C%20Linux-green)

## 🎯 What This App Does

This application helps you validate shipping documents by comparing:
- **CTN** - Number of Cartons
- **CBM** - Cubic Meters (Volume)
- **MEAS** - Measurements (Dimensions)

Results are shown with:
- ✅ **Green** - Documents match
- ❌ **Red** - Documents have differences

---

## 📋 Step-by-Step Installation Guide

### Step 1: Check if Python is Installed

Open your **Terminal** (on Mac) or **Command Prompt** (on Windows) and type:

```bash
python3 --version
```

If you see a version number like `Python 3.x.x`, you have Python installed. If not, download Python from [python.org](https://www.python.org/downloads/).

---

### Step 2: Navigate to the Application Folder

In your Terminal/Command Prompt, navigate to the folder where you saved the files:

```bash
cd /path/to/your/folder
```

For example, if the files are on your Desktop in a folder called "shipping_validator":
```bash
# On Mac:
cd ~/Desktop/shipping_validator

# On Windows:
cd C:\Users\YourName\Desktop\shipping_validator
```

---

### Step 3: Install Required Libraries

Run this command to install the PDF reading library:

```bash
pip3 install -r requirements.txt
```

**Or simply run:**
```bash
pip3 install pdfplumber
```

> **Note:** If `pip3` doesn't work, try `pip` instead.

---

### Step 4: Run the Application

Start the application with:

```bash
python3 shipping_validator.py
```

> **Note:** If `python3` doesn't work, try `python` instead.

---

## 🖥️ How to Use the Application

1. **Click "Browse"** next to "Document A" and select your first PDF file
2. **Click "Browse"** next to "Document B" and select your second PDF file
3. **Click the big blue "VALIDATE DOCUMENTS" button**
4. **View the results** at the bottom:
   - ✅ Green = Everything matches!
   - ❌ Red = Something is different (details will be shown)

---

## 🔧 Troubleshooting

### Problem: "python3 command not found"
**Solution:** Try using `python` instead of `python3`

### Problem: "pip3 command not found"
**Solution:** Try using `pip` instead of `pip3`

### Problem: "No module named pdfplumber"
**Solution:** Run `pip3 install pdfplumber` again

### Problem: "No module named tkinter"
**Solution:** 
- On Mac: `brew install python-tk`
- On Windows: Reinstall Python and make sure to check "tcl/tk" during installation
- On Linux: `sudo apt-get install python3-tk`

### Problem: Application doesn't extract data correctly
**Solution:** The app looks for common shipping terms like:
- CTN, CTNS, CARTONS, CARTON
- CBM, CUBIC METERS, M3
- MEAS, MEASUREMENT, DIMENSIONS, SIZE

Make sure your PDF documents contain these terms with the values nearby.

---

## 📁 Files Included

| File | Description |
|------|-------------|
| `shipping_validator.py` | The main application (all code in one file) |
| `requirements.txt` | List of required libraries |
| `README.md` | This instruction file |

---

## 💡 Tips

- Keep both PDF documents in an easy-to-find location
- The application extracts all text from PDFs and looks for shipping terms
- If values don't match, the app will show you exactly what's different

---

## 🆘 Need Help?

If you encounter any issues:
1. Make sure Python 3.7 or higher is installed
2. Make sure pdfplumber is installed (`pip3 install pdfplumber`)
3. Make sure your PDF files are readable (not password protected)

---

Made with ❤️ for easy document validation
