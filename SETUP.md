# ⚙️ Xyran AI - Setup Guide

This guide will walk you through setting up **Xyran AI** on Linux, macOS, and Windows systems.

---

## 📋 System Requirements

* **Python**: Python 3.10 or newer
* **Operating Systems & Native Tools**:
  * 🐧 **Linux**: GNOME Desktop with Wayland or X11 is recommended.
    * Requires `dbus`, `PyGObject` (for secure Wayland screenshot portal), and `xdotool` (for X11 focus).
  * 🍎 **macOS**: macOS 12+ (Monterey/Ventura/Sonoma).
    * Requires `Homebrew` for basic terminal utilities.
  * 🏁 **Windows**: Windows 10 or 11.
    * Requires `PowerShell` or `Git Bash` for terminal interface operations.

---

## 🛠️ Step 1: Install System Dependencies

Xyran relies on local OS features to automate browsers, handle focus, and capture desktop screenshots securely. Install requirements for your specific OS:

### 🐧 Linux
Choose the command for your distribution:
* **Fedora**:
  ```bash
  sudo dnf install -y python3-dbus python3-gobject xdotool brave-browser
  ```
* **Ubuntu / Debian**:
  ```bash
  sudo apt update
  sudo apt install -y python3-dbus python3-gi xdotool brave-browser
  ```
* **Arch Linux**:
  ```bash
  sudo pacman -S python-dbus python-gobject xdotool brave-browser
  ```

### 🍎 macOS
Make sure you have [Homebrew](https://brew.sh/) installed, then run:
```bash
brew install python xdotool
```

### 🏁 Windows
Simply download and install the latest [Python 3](https://www.python.org/downloads/) (ensure you tick **"Add Python to PATH"** during installation). Xyran will automatically run commands directly via CMD/PowerShell.

---

## 📦 Step 2: Create a Virtual Environment & Install Python Packages

1. **Clone the repository** (if you haven't already) and navigate to the directory:
   ```bash
   cd ~/Projects/XYRAN_AI/Xyran-Ai
   ```

2. **Create a Python Virtual Environment**:
   ```bash
   python3 -m venv venv
   ```

3. **Activate the Virtual Environment**:
   ```bash
   source venv/bin/activate
   ```

4. **Install PyGObject and DBus dependencies in the Venv (🐧 LINUX ONLY)**:
   > [!NOTE]
   > **macOS & Windows Users:** You can skip this step (Step 2.4) completely! Proceed directly to Step 2.5.
   
   To install `dbus-python` and `PyGObject` inside the virtual environment on Linux, you will need active system development headers:

   * **Fedora**:
     ```bash
     sudo dnf install -y gcc gobject-introspection-devel dbus-devel glib2-devel python3-devel
     ```
   * **Ubuntu / Debian**:
     ```bash
     sudo apt install -y gcc libgirepository1.0-dev libdbus-1-dev libglib2.0-dev python3-dev
     ```
   * **Arch Linux**:
     ```bash
     sudo pacman -S gcc gobject-introspection dbus glib2
     ```

   Once system headers are installed, install the Python libraries in your Venv:
   ```bash
   pip install --upgrade pip
   pip install pygobject dbus-python
   ```

5. **Install core requirements**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🔑 Step 3: Configure Environment Variables

1. Copy the template `.env.example` file to create your `.env` file:
   ```bash
   cp .env.example .env
   ```

2. Open the `.env` file in your favorite text editor:
   ```bash
   code .env # or gedit .env
   ```

3. Fill in your API keys and configuration parameters:
   * **`GROQ_API_KEY`**: Your API key from [Groq Console](https://console.groq.com/).
   * **`GEMINI_API_KEY`**: Your Google AI Studio API Key from [Google AI Studio](https://aistudio.google.com/).
   * **`NEWS_API_KEY`** (Optional): Key from [NewsAPI](https://newsapi.org/) if you want real-time world news capability.
   * **`AI_PROVIDER_MODE`**: Keep it set to `"smart"`. It will automatically choose the best model (Gemini for complex/vision requests, Groq for lightning-fast responses).

---

## 🚀 Step 4: Run Xyran AI

Activate the environment (if not already activated) and start Xyran:

```bash
source venv/bin/activate
python xyran.py
```

### 🧠 First Startup Note:
During the very first startup, Xyran's neural memory will automatically download the lightweight embedding model (`all-MiniLM-L6-v2`) via the `sentence-transformers` library (takes about ~90MB download). You'll see a launch indicator:
```text
>>> MODEL LOADING ONCE 🚀
>>> MODEL LOADED ✅
```
Subsequent startups will be instant!

---

## 🔍 Verification
You can verify that everything is working perfectly by typing:
* `hii` or `kese ho` (Checks basic chat and API routing).
* `screen dekho` (Checks the Wayland native portal screenshot utility and Llama Vision model).
* `brave khol ke google search karo fedora` (Checks multi-step automation).

Enjoy your personal AI companion! 🚀
