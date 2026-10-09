"""
TempCleaner Pro v3.0 - Windows System Cleaner
==================================================
Advanced system cleaner with browser cache/cookie/history clearing,
a disk space analyzer, a large-files finder, a startup-program manager,
automatic scheduled cleaning, before/after reports, dark mode, and an
optional password lock.

Made and developed by Deep 2026
Version: 3.0

Run modes:
    python TempCleaner_Pro_v3.py               -> normal GUI
    python TempCleaner_Pro_v3.py --auto-clean  -> silent clean (no GUI),
                                                   used by the scheduled task
"""

import os
import sys
import ctypes
import shutil
import string
import threading
import subprocess
import json
import hashlib
import secrets
import glob
import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# winreg is Windows-only. Import defensively so the file can still be
# opened/linted on non-Windows machines; all real use happens on Windows.
try:
    import winreg
except ImportError:
    winreg = None


APP_NAME = "TempCleanerPro"
SCHEDULED_TASK_NAME = "TempCleanerPro_AutoClean"


# ---------------------------------------------------------------------------
# Helpers (existing)
# ---------------------------------------------------------------------------

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin():
    """Re-launch this same script with admin rights via UAC prompt."""
    params = " ".join([f'"{a}"' for a in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{os.path.abspath(__file__)}" {params}', None, 1
    )
    sys.exit(0)


def human_size(num_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def folder_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    try:
        for root, dirs, files in os.walk(path, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except Exception:
        pass
    return total


def get_file_size(file_path):
    """Get size of a single file."""
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
    except OSError:
        pass
    return 0


def clear_folder_contents(path, log_fn):
    """Delete everything INSIDE a folder, but keep the folder itself.
    Skips files that are locked/in-use. Returns bytes freed."""
    freed = 0
    if not os.path.exists(path):
        log_fn(f"  (skip - not found) {path}")
        return 0

    try:
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            try:
                if os.path.isdir(full) and not os.path.islink(full):
                    size_before = folder_size(full)
                    shutil.rmtree(full, ignore_errors=True)
                    remaining = folder_size(full) if os.path.exists(full) else 0
                    freed += (size_before - remaining)
                else:
                    size = os.path.getsize(full)
                    os.remove(full)
                    freed += size
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return freed


def clear_specific_files(file_patterns, log_fn):
    """Delete specific files matching patterns. Returns bytes freed."""
    freed = 0
    for pattern in file_patterns:
        try:
            for file_path in glob.glob(pattern):
                try:
                    if os.path.isfile(file_path):
                        size = get_file_size(file_path)
                        os.remove(file_path)
                        freed += size
                except (PermissionError, OSError):
                    # File might be locked (browser running)
                    pass
        except Exception:
            pass
    return freed


def clear_browser_data(browser_name, log_fn):
    """Clear browser cache, cookies, and HISTORY. Returns bytes freed."""
    freed = 0
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")

    if browser_name == "Chrome":
        paths = [
            os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache"),
            os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cookies"),
            os.path.join(local, "Google", "Chrome", "User Data", "Default", "History"),
            os.path.join(local, "Google", "Chrome", "User Data", "Default", "Visited Links"),
            os.path.join(local, "Google", "Chrome", "User Data", "Default", "Top Sites"),
        ]

    elif browser_name == "Firefox":
        profile_path = os.path.join(roaming, "Mozilla", "Firefox", "Profiles")
        paths = []
        if os.path.exists(profile_path):
            for profile in glob.glob(os.path.join(profile_path, "*")):
                if os.path.isdir(profile):
                    paths.extend([
                        os.path.join(profile, "cache2"),
                        os.path.join(profile, "startupCache"),
                        os.path.join(profile, "places.sqlite"),
                        os.path.join(profile, "places.sqlite-wal"),
                        os.path.join(profile, "places.sqlite-shm"),
                        os.path.join(profile, "cookies.sqlite"),
                    ])

    elif browser_name == "Edge":
        paths = [
            os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache"),
            os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cookies"),
            os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "History"),
            os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Visited Links"),
        ]

    elif browser_name == "Opera":
        paths = [
            os.path.join(roaming, "Opera Software", "Opera Stable", "Cache"),
            os.path.join(roaming, "Opera Software", "Opera Stable", "Cookies"),
            os.path.join(roaming, "Opera Software", "Opera Stable", "History"),
            os.path.join(roaming, "Opera Software", "Opera Stable", "Visited Links"),
        ]

    elif browser_name == "Brave":
        paths = [
            os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cache"),
            os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cookies"),
            os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "History"),
            os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Visited Links"),
        ]
    else:
        paths = []

    for path in paths:
        if path.endswith(".sqlite") or path.endswith("History"):
            freed += clear_specific_files([path], log_fn)
        else:
            freed += clear_folder_contents(path, log_fn)

    return freed


def empty_recycle_bin(log_fn):
    try:
        SHERB_NOCONFIRMATION = 0x00000001
        SHERB_NOPROGRESSUI = 0x00000002
        SHERB_NOSOUND = 0x00000004
        ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None,
            SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        )
        return True
    except Exception as e:
        log_fn(f"  Recycle Bin error: {e}")
        return False


# ---------------------------------------------------------------------------
# Target locations
# ---------------------------------------------------------------------------

def get_targets():
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    userprofile = os.environ.get("USERPROFILE", "")
    windir = os.environ.get("WINDIR", r"C:\Windows")
    temp = os.environ.get("TEMP", "")

    return [
        # ===== SYSTEM TEMP =====
        {
            "key": "user_temp",
            "label": "User Temp Files",
            "category": "System",
            "path": temp,
            "admin_needed": False,
            "default": True,
        },
        {
            "key": "windows_temp",
            "label": "Windows Temp Folder",
            "category": "System",
            "path": os.path.join(windir, "Temp"),
            "admin_needed": True,
            "default": True,
        },
        {
            "key": "prefetch",
            "label": "Application Prefetch",
            "category": "System",
            "path": os.path.join(windir, "Prefetch"),
            "admin_needed": True,
            "default": True,
        },
        {
            "key": "winupdate",
            "label": "Windows Update Cache",
            "category": "System",
            "path": os.path.join(windir, "SoftwareDistribution", "Download"),
            "admin_needed": True,
            "default": True,
        },
        # ===== CACHES & RECENT =====
        {
            "key": "recent",
            "label": "Recent Files List",
            "category": "Caches",
            "path": os.path.join(roaming, "Microsoft", "Windows", "Recent"),
            "admin_needed": False,
            "default": True,
        },
        {
            "key": "thumbcache",
            "label": "Thumbnail Cache",
            "category": "Caches",
            "path": os.path.join(local, "Microsoft", "Windows", "Explorer"),
            "admin_needed": False,
            "default": True,
        },
        {
            "key": "wer",
            "label": "Windows Error Reports",
            "category": "Caches",
            "path": r"C:\ProgramData\Microsoft\Windows\WER",
            "admin_needed": True,
            "default": False,
        },
        # ===== BROWSERS WITH HISTORY =====
        {
            "key": "chrome_cache",
            "label": "Google Chrome (Cache, Cookies, History)",
            "category": "Browsers",
            "browser_name": "Chrome",
            "is_browser": True,
            "admin_needed": False,
            "default": True,
        },
        {
            "key": "firefox_cache",
            "label": "Mozilla Firefox (Cache, Cookies, History)",
            "category": "Browsers",
            "browser_name": "Firefox",
            "is_browser": True,
            "admin_needed": False,
            "default": True,
        },
        {
            "key": "edge_cache",
            "label": "Microsoft Edge (Cache, Cookies, History)",
            "category": "Browsers",
            "browser_name": "Edge",
            "is_browser": True,
            "admin_needed": False,
            "default": True,
        },
        {
            "key": "opera_cache",
            "label": "Opera (Cache, Cookies, History)",
            "category": "Browsers",
            "browser_name": "Opera",
            "is_browser": True,
            "admin_needed": False,
            "default": False,
        },
        {
            "key": "brave_cache",
            "label": "Brave Browser (Cache, Cookies, History)",
            "category": "Browsers",
            "browser_name": "Brave",
            "is_browser": True,
            "admin_needed": False,
            "default": False,
        },
        # ===== OTHER =====
        {
            "key": "recyclebin",
            "label": "Recycle Bin",
            "category": "Other",
            "path": None,
            "admin_needed": False,
            "default": True,
        },
    ]


# ---------------------------------------------------------------------------
# App config (settings, password hash) - stored in %APPDATA%\TempCleanerPro
# ---------------------------------------------------------------------------

def get_config_dir():
    roaming = os.environ.get("APPDATA", os.path.expanduser("~"))
    path = os.path.join(roaming, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_config_path():
    return os.path.join(get_config_dir(), "config.json")


def load_config():
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config):
    try:
        with open(get_config_path(), "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def hash_password(password, salt=None):
    """Return (salt_hex, hash_hex) using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return salt, digest.hex()


def verify_password(password, config):
    salt = config.get("pw_salt")
    stored_hash = config.get("pw_hash")
    if not salt or not stored_hash:
        return True  # no password set
    _, candidate_hash = hash_password(password, salt)
    return secrets.compare_digest(candidate_hash, stored_hash)


def set_password(password, config):
    salt, pw_hash = hash_password(password)
    config["pw_salt"] = salt
    config["pw_hash"] = pw_hash
    save_config(config)


def clear_password(config):
    config.pop("pw_salt", None)
    config.pop("pw_hash", None)
    save_config(config)


# ---------------------------------------------------------------------------
# Disk Space Analyzer
# ---------------------------------------------------------------------------

def list_available_drives():
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)
    return drives or ["C:\\"]


def get_disk_breakdown(drive="C:\\", progress_fn=None):
    """Return an ordered dict-like list of (category, bytes) for a rough
    breakdown of what is using space on `drive`, plus free/total space.
    This is an approximation based on well-known folders, not a byte-exact
    accounting (some system-internal usage will fall into 'Other')."""
    total, used, free = shutil.disk_usage(drive)

    windir = os.environ.get("WINDIR", os.path.join(drive, "Windows"))
    program_files = [
        os.environ.get("PROGRAMFILES", os.path.join(drive, "Program Files")),
        os.environ.get("PROGRAMFILES(X86)", os.path.join(drive, "Program Files (x86)")),
        os.environ.get("PROGRAMDATA", os.path.join(drive, "ProgramData")),
    ]
    userprofile = os.environ.get("USERPROFILE", "")

    if progress_fn:
        progress_fn("Scanning Windows folder...")
    windows_size = folder_size(windir) if os.path.exists(windir) else 0

    if progress_fn:
        progress_fn("Scanning Program Files...")
    programs_size = sum(folder_size(p) for p in program_files if p and os.path.exists(p))

    if progress_fn:
        progress_fn("Scanning your user folder...")
    user_size = folder_size(userprofile) if userprofile and os.path.exists(userprofile) else 0

    other_size = max(used - windows_size - programs_size - user_size, 0)

    return {
        "breakdown": [
            ("Windows System", windows_size),
            ("Programs", programs_size),
            ("User Files", user_size),
            ("Other", other_size),
        ],
        "total": total,
        "used": used,
        "free": free,
    }


# ---------------------------------------------------------------------------
# Large Files Finder
# ---------------------------------------------------------------------------

def find_large_files(root_path, min_size_bytes, stop_flag=None, max_results=500):
    """Walk root_path and return [(full_path, size_bytes), ...] for files
    at least min_size_bytes, largest first. stop_flag is a threading.Event
    that can be set to cancel an in-progress scan early."""
    results = []
    if not root_path or not os.path.exists(root_path):
        return results

    for current_root, dirs, files in os.walk(root_path, onerror=lambda e: None):
        if stop_flag is not None and stop_flag.is_set():
            break
        for f in files:
            full = os.path.join(current_root, f)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size >= min_size_bytes:
                results.append((full, size))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:max_results]


def delete_file_safe(path):
    try:
        os.remove(path)
        return True, None
    except OSError as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Startup Programs Manager (HKCU/HKLM ...CurrentVersion\Run)
# ---------------------------------------------------------------------------

DISABLED_STARTUP_KEY = r"Software\TempCleanerPro\DisabledStartup"


def _startup_run_keys():
    if winreg is None:
        return []
    return [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", False, "Current User"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", True, "All Users"),
    ]


def list_startup_items():
    """Return currently-enabled startup entries from the Run registry keys.
    Note: this only covers the common Run-key startup mechanism, not every
    possible autostart location (services, scheduled tasks, Startup folder)."""
    items = []
    if winreg is None:
        return items
    for hive, subkey, needs_admin, scope_label in _startup_run_keys():
        try:
            with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    items.append({
                        "name": name,
                        "command": value,
                        "hive": hive,
                        "subkey": subkey,
                        "admin_needed": needs_admin,
                        "scope": scope_label,
                    })
                    i += 1
        except FileNotFoundError:
            continue
        except PermissionError:
            continue
    return items


def list_disabled_startup_items():
    """Return startup entries this app has previously disabled (and backed
    up), so they can be re-enabled."""
    items = []
    if winreg is None:
        return items
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DISABLED_STARTUP_KEY, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                items.append({"name": name, "command": value})
                i += 1
    except FileNotFoundError:
        pass
    return items


def disable_startup_item(item):
    """Back up a startup entry into our own registry key, then remove it
    from the Run key so it no longer launches at sign-in. Reversible via
    enable_startup_item()."""
    if winreg is None:
        return False, "Not running on Windows."
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DISABLED_STARTUP_KEY) as bkey:
            winreg.SetValueEx(bkey, item["name"], 0, winreg.REG_SZ, item["command"])
        with winreg.OpenKey(item["hive"], item["subkey"], 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, item["name"])
        return True, None
    except PermissionError:
        return False, "Access denied - try running as Administrator."
    except OSError as e:
        return False, str(e)


def enable_startup_item(name):
    """Restore a previously-disabled entry back into HKCU's Run key."""
    if winreg is None:
        return False, "Not running on Windows."
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DISABLED_STARTUP_KEY, 0, winreg.KEY_READ) as bkey:
            value, _ = winreg.QueryValueEx(bkey, name)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as rkey:
            winreg.SetValueEx(rkey, name, 0, winreg.REG_SZ, value)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DISABLED_STARTUP_KEY, 0, winreg.KEY_SET_VALUE) as bkey:
            winreg.DeleteValue(bkey, name)
        return True, None
    except OSError as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Automatic Scheduling (Windows Task Scheduler via schtasks.exe)
# ---------------------------------------------------------------------------

def _launch_command_for_task():
    """Build the command line used to silently re-launch this app for a
    scheduled clean. Handles both a frozen .exe build and a plain .py run."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --auto-clean'
    pythonw = sys.executable
    if pythonw.lower().endswith("python.exe"):
        candidate = pythonw[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(candidate):
            pythonw = candidate
    script = os.path.abspath(__file__)
    return f'"{pythonw}" "{script}" --auto-clean'


def create_scheduled_task(frequency, time_str="02:00"):
    """frequency: 'DAILY', 'WEEKLY', or 'ONLOGON'."""
    command = _launch_command_for_task()
    args = ["schtasks", "/Create", "/TN", SCHEDULED_TASK_NAME, "/TR", command, "/F"]
    if frequency == "ONLOGON":
        args += ["/SC", "ONLOGON"]
    else:
        args += ["/SC", frequency, "/ST", time_str]
        if frequency == "WEEKLY":
            args += ["/D", "SUN"]
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
        return True, "Scheduled task created."
    except FileNotFoundError:
        return False, "schtasks.exe not found (this feature requires Windows)."
    except subprocess.CalledProcessError as e:
        return False, (e.stderr or str(e)).strip()


def delete_scheduled_task():
    try:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", SCHEDULED_TASK_NAME, "/F"],
            check=True, capture_output=True, text=True,
        )
        return True, "Scheduled task removed."
    except FileNotFoundError:
        return False, "schtasks.exe not found (this feature requires Windows)."
    except subprocess.CalledProcessError as e:
        return False, (e.stderr or str(e)).strip()


def scheduled_task_exists():
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", SCHEDULED_TASK_NAME],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Before/After Reports
# ---------------------------------------------------------------------------

def get_reports_dir():
    path = os.path.join(get_config_dir(), "Reports")
    os.makedirs(path, exist_ok=True)
    return path


def build_report_text(results, total_freed, elapsed_seconds, free_before=None, free_after=None):
    lines = []
    lines.append("TEMPCLEANER PRO - CLEANING REPORT")
    lines.append("=" * 50)
    lines.append(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("-" * 50)
    for label, freed in results:
        lines.append(f"{label:<35}{human_size(freed):>15}")
    lines.append("-" * 50)
    lines.append(f"{'Total Freed':<35}{human_size(total_freed):>15}")
    mins, secs = divmod(int(elapsed_seconds), 60)
    lines.append(f"{'Time Taken':<35}{f'{mins}:{secs:02d}':>15}")
    if free_before is not None and free_after is not None:
        lines.append("-" * 50)
        lines.append(f"{'Free space before':<35}{human_size(free_before):>15}")
        lines.append(f"{'Free space after':<35}{human_size(free_after):>15}")
    lines.append("=" * 50)
    return "\n".join(lines)


def save_report(report_text):
    filename = f"CleanReport_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    path = os.path.join(get_reports_dir(), filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_text)
    return path


def list_saved_reports():
    reports_dir = get_reports_dir()
    files = glob.glob(os.path.join(reports_dir, "CleanReport_*.txt"))
    files.sort(key=os.path.getmtime, reverse=True)
    return files


# ---------------------------------------------------------------------------
# Silent auto-clean (used by the scheduled task, no GUI)
# ---------------------------------------------------------------------------

def run_silent_clean():
    admin = is_admin()
    targets = [t for t in get_targets() if t["default"] and not (t.get("admin_needed") and not admin)]

    drive = os.environ.get("SYSTEMDRIVE", "C:") + "\\"
    try:
        _, _, free_before = shutil.disk_usage(drive)
    except OSError:
        free_before = None

    start_time = datetime.datetime.now()
    results = []
    total_freed = 0
    noop_log = lambda text: None

    for t in targets:
        if t["key"] == "recyclebin":
            empty_recycle_bin(noop_log)
            results.append((t["label"], 0))
        elif t.get("is_browser"):
            freed = clear_browser_data(t.get("browser_name", "Unknown"), noop_log)
            total_freed += freed
            results.append((t["label"], freed))
        else:
            freed = clear_folder_contents(t["path"], noop_log)
            total_freed += freed
            results.append((t["label"], freed))

    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    try:
        _, _, free_after = shutil.disk_usage(drive)
    except OSError:
        free_after = None

    report = build_report_text(results, total_freed, elapsed, free_before, free_after)
    save_report(report)


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------

LIGHT_THEME = {
    "bg": "#f5f5f5",
    "panel_bg": "white",
    "primary": "#0d47a1",
    "success": "#2e7d32",
    "warning": "#f57c00",
    "danger": "#c62828",
    "text": "#333333",
    "muted": "#666666",
    "subtitle": "#e0e0e0",
    "status_bg": "#eeeeee",
}

DARK_THEME = {
    "bg": "#1e1e1e",
    "panel_bg": "#2a2a2a",
    "primary": "#1565c0",
    "success": "#43a047",
    "warning": "#fb8c00",
    "danger": "#e53935",
    "text": "#e0e0e0",
    "muted": "#aaaaaa",
    "subtitle": "#cfd8dc",
    "status_bg": "#252525",
}


# ---------------------------------------------------------------------------
# Login lock (optional password protection)
# ---------------------------------------------------------------------------

def prompt_login(config):
    """Show a small login window if a password is set. Returns True if the
    user may proceed (no password set, or correct password entered)."""
    if not config.get("pw_hash"):
        return True

    result = {"ok": False}
    login = tk.Tk()
    login.title("TempCleaner Pro - Locked")
    login.geometry("340x180")
    login.resizable(False, False)
    login.configure(bg="#1e1e1e")

    tk.Label(login, text="🔒  TempCleaner Pro", font=("Segoe UI", 14, "bold"),
              bg="#1e1e1e", fg="white").pack(pady=(20, 6))
    tk.Label(login, text="Enter password to continue", font=("Segoe UI", 9),
              bg="#1e1e1e", fg="#cccccc").pack(pady=(0, 10))

    pw_var = tk.StringVar()
    entry = tk.Entry(login, textvariable=pw_var, show="*", font=("Segoe UI", 11), justify="center")
    entry.pack(pady=4, ipady=4, padx=30, fill="x")
    entry.focus_set()

    error_label = tk.Label(login, text="", font=("Segoe UI", 8), bg="#1e1e1e", fg="#ef5350")
    error_label.pack()

    attempts = {"count": 0}

    def try_login(event=None):
        if verify_password(pw_var.get(), config):
            result["ok"] = True
            login.destroy()
        else:
            attempts["count"] += 1
            remaining = max(0, 5 - attempts["count"])
            error_label.config(text=f"Incorrect password ({remaining} attempts left)")
            pw_var.set("")
            if attempts["count"] >= 5:
                login.destroy()

    entry.bind("<Return>", try_login)
    tk.Button(login, text="Unlock", command=try_login, bg="#1565c0", fg="white",
               relief="flat", padx=16, pady=6).pack(pady=10)

    login.mainloop()
    return result["ok"]


# ---------------------------------------------------------------------------
# GUI - tabbed layout
# ---------------------------------------------------------------------------

class TempCleanerApp:
    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.root.title("TempCleaner Pro - System Cleaner")
        self.root.geometry("780x820")
        self.root.minsize(720, 700)

        self.theme_name = config.get("theme", "light")
        self.colors = DARK_THEME if self.theme_name == "dark" else LIGHT_THEME

        self.targets = get_targets()
        self.check_vars = {}
        self.total_items = 0

        # Large files finder state
        self.large_files_results = []
        self.large_scan_stop = threading.Event()

        # Disk analyzer state
        self.disk_breakdown_cache = None

        self._build_ui()

    # -- theme handling ----------------------------------------------------

    def toggle_dark_mode(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.colors = DARK_THEME if self.theme_name == "dark" else LIGHT_THEME
        self.config["theme"] = self.theme_name
        save_config(self.config)
        for child in self.root.winfo_children():
            child.destroy()
        self._build_ui()

    # -- top-level build -----------------------------------------------------

    def _build_ui(self):
        c = self.colors
        self.root.configure(bg=c["bg"])

        self._build_menu()
        self._build_header()

        if not is_admin():
            self._build_admin_warning()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        self.tab_clean = tk.Frame(self.notebook, bg=c["bg"])
        self.tab_disk = tk.Frame(self.notebook, bg=c["bg"])
        self.tab_large = tk.Frame(self.notebook, bg=c["bg"])
        self.tab_startup = tk.Frame(self.notebook, bg=c["bg"])
        self.tab_schedule = tk.Frame(self.notebook, bg=c["bg"])
        self.tab_reports = tk.Frame(self.notebook, bg=c["bg"])

        self.notebook.add(self.tab_clean, text="🧹 Clean")
        self.notebook.add(self.tab_disk, text="📊 Disk Analyzer")
        self.notebook.add(self.tab_large, text="📁 Large Files")
        self.notebook.add(self.tab_startup, text="🔧 Startup")
        self.notebook.add(self.tab_schedule, text="⏰ Scheduler")
        self.notebook.add(self.tab_reports, text="📝 Reports")

        self._build_clean_tab(self.tab_clean)
        self._build_disk_tab(self.tab_disk)
        self._build_large_files_tab(self.tab_large)
        self._build_startup_tab(self.tab_startup)
        self._build_schedule_tab(self.tab_schedule)
        self._build_reports_tab(self.tab_reports)

        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var, anchor="w",
            bg=c["status_bg"], fg=c["muted"], font=("Segoe UI", 8), padx=14, pady=6
        )
        status_bar.pack(fill="x", side="bottom")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TProgressbar", background=c["success"])

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Set / Change Password...", command=self.on_set_password)
        settings_menu.add_command(label="Remove Password", command=self.on_remove_password)
        settings_menu.add_separator()
        label = "Switch to Light Mode" if self.theme_name == "dark" else "Switch to Dark Mode"
        settings_menu.add_command(label=label, command=self.toggle_dark_mode)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        self.root.config(menu=menubar)

    def _build_header(self):
        c = self.colors
        header = tk.Frame(self.root, bg=c["primary"], height=80)
        header.pack(fill="x")

        title = tk.Label(header, text="🧹 TempCleaner Pro", font=("Segoe UI", 20, "bold"),
                          bg=c["primary"], fg="white")
        title.pack(pady=(12, 0))

        subtitle = tk.Label(header, text="System Cleaner - v3.0 Professional Edition",
                             font=("Segoe UI", 10), bg=c["primary"], fg=c["subtitle"])
        subtitle.pack(pady=(0, 4))

        credit = tk.Label(header, text="Made and developed by Deep 2026",
                           font=("Segoe UI", 8), bg=c["primary"], fg=c["subtitle"])
        credit.pack(pady=(0, 10))

    def _build_admin_warning(self):
        warn = tk.Label(
            self.root,
            text="⚠️  Not running as Administrator - some items and startup entries are limited",
            bg="#fff3e0", fg="#e65100", font=("Segoe UI", 9),
            anchor="w", justify="left", padx=15, pady=8
        )
        warn.pack(fill="x")
        admin_btn = tk.Button(
            self.root, text="🔧 Restart as Administrator",
            command=relaunch_as_admin, bg=self.colors["warning"], fg="white",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=6
        )
        admin_btn.pack(pady=(0, 8))

    # -- settings menu actions ----------------------------------------------

    def on_set_password(self):
        pw1 = simpledialog.askstring("Set Password", "Enter a new password:", show="*", parent=self.root)
        if pw1 is None:
            return
        if len(pw1) < 4:
            messagebox.showwarning("Too Short", "Please use at least 4 characters.")
            return
        pw2 = simpledialog.askstring("Confirm Password", "Re-enter the password:", show="*", parent=self.root)
        if pw1 != pw2:
            messagebox.showerror("Mismatch", "Passwords did not match. Please try again.")
            return
        set_password(pw1, self.config)
        messagebox.showinfo("Password Set", "TempCleaner Pro will now ask for this password on launch.")

    def on_remove_password(self):
        if not self.config.get("pw_hash"):
            messagebox.showinfo("No Password", "No password is currently set.")
            return
        clear_password(self.config)
        messagebox.showinfo("Password Removed", "Password protection has been turned off.")

    # -- CLEAN TAB ------------------------------------------------------------

    def _build_clean_tab(self, parent):
        c = self.colors
        main_frame = tk.Frame(parent, bg=c["bg"])
        main_frame.pack(fill="both", expand=True, padx=4, pady=6)

        self.category_frames = {}
        categories_in_order = ["System", "Caches", "Browsers", "Other"]

        for category in categories_in_order:
            cat_frame = tk.LabelFrame(main_frame, text=f"📁 {category}",
                                       font=("Segoe UI", 10, "bold"),
                                       bg=c["panel_bg"], fg=c["primary"], padx=10, pady=6,
                                       relief="flat", bd=1)
            cat_frame.pack(fill="x", pady=(0, 8))
            self.category_frames[category] = cat_frame

        for t in self.targets:
            category = t.get("category", "Other")
            var = tk.BooleanVar(value=t["default"])
            self.check_vars[t["key"]] = var
            self.total_items += 1

            label_text = t["label"]
            if t.get("admin_needed"):
                label_text += "  🔒 (Admin)"

            cb = tk.Checkbutton(
                self.category_frames[category],
                text=label_text, variable=var, anchor="w",
                bg=c["panel_bg"], font=("Segoe UI", 9),
                selectcolor=c["panel_bg"], activebackground=c["panel_bg"],
                fg=c["text"]
            )
            cb.pack(fill="x", pady=2)

        btn_frame = tk.Frame(main_frame, bg=c["bg"])
        btn_frame.pack(pady=6)

        self.clean_btn = tk.Button(
            btn_frame, text="🧹  CLEAN NOW", font=("Segoe UI", 12, "bold"),
            bg=c["success"], fg="white", activebackground="#1b5e20",
            width=22, height=2, command=self.start_clean, relief="flat",
            cursor="hand2"
        )
        self.clean_btn.grid(row=0, column=0, padx=6)

        select_all_btn = tk.Button(
            btn_frame, text="✓ Select All", command=self.select_all,
            bg="#616161", fg="white", font=("Segoe UI", 9),
            relief="flat", padx=12, pady=8, cursor="hand2"
        )
        select_all_btn.grid(row=0, column=1, padx=3)

        select_none_btn = tk.Button(
            btn_frame, text="✗ Select None", command=self.select_none,
            bg="#616161", fg="white", font=("Segoe UI", 9),
            relief="flat", padx=12, pady=8, cursor="hand2"
        )
        select_none_btn.grid(row=0, column=2, padx=3)

        progress_frame = tk.Frame(main_frame, bg=c["bg"])
        progress_frame.pack(fill="x", pady=(4, 0))

        progress_label_frame = tk.Frame(progress_frame, bg=c["bg"])
        progress_label_frame.pack(fill="x")

        self.progress_label = tk.Label(
            progress_label_frame, text="Ready", font=("Segoe UI", 9, "bold"),
            bg=c["bg"], fg=c["text"]
        )
        self.progress_label.pack(side="left")

        self.percent_label = tk.Label(
            progress_label_frame, text="0%", font=("Segoe UI", 9, "bold"),
            bg=c["bg"], fg=c["primary"]
        )
        self.percent_label.pack(side="right")

        self.progress = ttk.Progressbar(
            progress_frame, mode="determinate", length=650,
            style="TProgressbar"
        )
        self.progress.pack(pady=8)

        log_frame = tk.Frame(main_frame, bg=c["bg"])
        log_frame.pack(fill="both", expand=True, pady=(0, 4))

        log_label = tk.Label(log_frame, text="Activity Log", font=("Segoe UI", 9, "bold"),
                              bg=c["bg"], fg=c["text"])
        log_label.pack(anchor="w", pady=(0, 4))

        self.log_box = tk.Text(
            log_frame, height=8, font=("Consolas", 8),
            state="disabled", bg=c["panel_bg"], fg=c["text"], relief="flat", bd=1
        )
        self.log_box.pack(fill="both", expand=True, side="left")

        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_box["yscrollcommand"] = scrollbar.set

    def select_all(self):
        for v in self.check_vars.values():
            v.set(True)

    def select_none(self):
        for v in self.check_vars.values():
            v.set(False)

    def log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")
        self.root.update_idletasks()

    def start_clean(self):
        self.clean_btn.config(state="disabled", text="⏳  Cleaning...")
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")
        self.status_var.set("Scanning and cleaning...")
        self.progress_label.config(text="Starting...")

        selected = [t for t in self.targets if self.check_vars[t["key"]].get()]
        self.progress["maximum"] = 100
        self.progress["value"] = 0

        thread = threading.Thread(target=self._clean_worker, args=(selected,), daemon=True)
        thread.start()

    def update_progress(self, current, total):
        if total > 0:
            percentage = int((current / total) * 100)
        else:
            percentage = 0
        self.progress["value"] = percentage
        self.percent_label.config(text=f"{percentage}%")
        self.root.update_idletasks()

    def _clean_worker(self, selected):
        drive = os.environ.get("SYSTEMDRIVE", "C:") + "\\"
        try:
            _, _, free_before = shutil.disk_usage(drive)
        except OSError:
            free_before = None

        start_time = datetime.datetime.now()
        total_freed = 0
        admin = is_admin()
        completed = 0
        report_rows = []

        for t in selected:
            self.log(f">>> {t['label']}")

            if t.get("admin_needed") and not admin:
                self.log("    ⊘ Skipped - requires Administrator rights")
                report_rows.append((t["label"], 0))
            elif t["key"] == "recyclebin":
                ok = empty_recycle_bin(self.log)
                if ok:
                    self.log("    ✓ Recycle Bin emptied")
                else:
                    self.log("    ⊘ Could not empty Recycle Bin")
                report_rows.append((t["label"], 0))
            elif t.get("is_browser"):
                browser_name = t.get("browser_name", "Unknown")
                freed = clear_browser_data(browser_name, self.log)
                total_freed += freed
                report_rows.append((t["label"], freed))
                self.log(f"    ✓ Freed {human_size(freed)}")
            else:
                freed = clear_folder_contents(t["path"], self.log)
                total_freed += freed
                report_rows.append((t["label"], freed))
                self.log(f"    ✓ Freed {human_size(freed)}")

            completed += 1
            self.update_progress(completed, len(selected))
            self.status_var.set(f"Processing {completed}/{len(selected)}...")

        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        try:
            _, _, free_after = shutil.disk_usage(drive)
        except OSError:
            free_after = None

        self.log(f"\n{'='*50}")
        self.log("✓ CLEANING COMPLETE")
        self.log(f"Total space freed: {human_size(total_freed)}")
        self.log(f"{'='*50}")

        report_text = build_report_text(report_rows, total_freed, elapsed, free_before, free_after)
        try:
            report_path = save_report(report_text)
            self.log(f"Report saved: {report_path}")
        except OSError as e:
            self.log(f"Could not save report: {e}")

        self.progress["value"] = 100
        self.percent_label.config(text="100%")
        self.status_var.set(f"✓ Done! Freed {human_size(total_freed)}")
        self.progress_label.config(text="Complete")
        self.clean_btn.config(state="normal", text="🧹  CLEAN NOW")

        if hasattr(self, "refresh_reports_list"):
            self.root.after(0, self.refresh_reports_list)

        messagebox.showinfo(
            "TempCleaner Pro - Success",
            f"✓ Cleaning Complete!\n\nTotal space freed:\n{human_size(total_freed)}"
        )

    # -- DISK ANALYZER TAB ----------------------------------------------------

    PIE_COLORS = ["#0d47a1", "#2e7d32", "#f57c00", "#9e9e9e", "#6a1b9a"]

    def _build_disk_tab(self, parent):
        c = self.colors
        top = tk.Frame(parent, bg=c["bg"])
        top.pack(fill="x", padx=8, pady=8)

        tk.Label(top, text="Drive:", bg=c["bg"], fg=c["text"], font=("Segoe UI", 9)).pack(side="left")
        self.drive_var = tk.StringVar(value=list_available_drives()[0])
        drive_menu = ttk.Combobox(top, textvariable=self.drive_var, values=list_available_drives(),
                                   width=6, state="readonly")
        drive_menu.pack(side="left", padx=(6, 12))

        self.disk_scan_btn = tk.Button(
            top, text="📊 Scan Drive", command=self.start_disk_scan,
            bg=c["primary"], fg="white", relief="flat", padx=12, pady=6, cursor="hand2"
        )
        self.disk_scan_btn.pack(side="left")

        self.disk_status_label = tk.Label(top, text="", bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9))
        self.disk_status_label.pack(side="left", padx=12)

        note = tk.Label(
            parent,
            text="This is an approximate breakdown based on well-known folders. "
                 "Scanning Windows and Program Files can take a minute or two.",
            bg=c["bg"], fg=c["muted"], font=("Segoe UI", 8), wraplength=700, justify="left"
        )
        note.pack(fill="x", padx=8)

        body = tk.Frame(parent, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=8, pady=8)

        self.disk_canvas = tk.Canvas(body, width=320, height=320, bg=c["panel_bg"], highlightthickness=0)
        self.disk_canvas.pack(side="left", padx=(0, 20))

        self.disk_legend_frame = tk.Frame(body, bg=c["bg"])
        self.disk_legend_frame.pack(side="left", fill="both", expand=True)

        self._draw_disk_placeholder()

    def _draw_disk_placeholder(self):
        self.disk_canvas.delete("all")
        self.disk_canvas.create_oval(20, 20, 300, 300, outline=self.colors["muted"], width=2, dash=(4, 2))
        self.disk_canvas.create_text(160, 160, text="Scan a drive\nto see the breakdown",
                                      fill=self.colors["muted"], font=("Segoe UI", 10), justify="center")

    def start_disk_scan(self):
        self.disk_scan_btn.config(state="disabled", text="⏳ Scanning...")
        self.disk_status_label.config(text="Scanning...")
        drive = self.drive_var.get()
        thread = threading.Thread(target=self._disk_scan_worker, args=(drive,), daemon=True)
        thread.start()

    def _disk_scan_worker(self, drive):
        def progress(msg):
            self.root.after(0, lambda: self.disk_status_label.config(text=msg))

        data = get_disk_breakdown(drive, progress_fn=progress)
        self.root.after(0, lambda: self._on_disk_scan_done(data))

    def _on_disk_scan_done(self, data):
        self.disk_breakdown_cache = data
        self.disk_scan_btn.config(state="normal", text="📊 Scan Drive")
        self.disk_status_label.config(text=f"Total: {human_size(data['total'])}  |  Free: {human_size(data['free'])}")
        self._render_disk_chart(data)

    def _render_disk_chart(self, data):
        c = self.colors
        canvas = self.disk_canvas
        canvas.delete("all")

        breakdown = data["breakdown"]
        used_total = sum(v for _, v in breakdown) or 1
        cx, cy, r = 160, 160, 130
        start_angle = 0.0
        for (label, value), color in zip(breakdown, self.PIE_COLORS):
            extent = 360.0 * (value / used_total) if used_total else 0
            if extent <= 0:
                continue
            canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                               start=start_angle, extent=extent,
                               fill=color, outline=c["panel_bg"], width=2)
            start_angle += extent

        canvas.create_text(cx, cy, text=f"{human_size(data['used'])}\nused",
                            fill=c["text"], font=("Segoe UI", 10, "bold"), justify="center")

        for widget in self.disk_legend_frame.winfo_children():
            widget.destroy()

        tk.Label(self.disk_legend_frame, text="What's using your space", font=("Segoe UI", 11, "bold"),
                 bg=c["bg"], fg=c["text"]).pack(anchor="w", pady=(0, 8))

        for (label, value), color in zip(breakdown, self.PIE_COLORS):
            pct = (value / used_total * 100) if used_total else 0
            row = tk.Frame(self.disk_legend_frame, bg=c["bg"])
            row.pack(fill="x", pady=3)
            swatch = tk.Canvas(row, width=14, height=14, bg=c["bg"], highlightthickness=0)
            swatch.create_rectangle(0, 0, 14, 14, fill=color, outline="")
            swatch.pack(side="left", padx=(0, 8))
            tk.Label(row, text=label, bg=c["bg"], fg=c["text"], font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
            tk.Label(row, text=f"{human_size(value)}  ({pct:.1f}%)", bg=c["bg"], fg=c["muted"],
                     font=("Segoe UI", 9)).pack(side="left")

        free_row = tk.Frame(self.disk_legend_frame, bg=c["bg"])
        free_row.pack(fill="x", pady=(10, 3))
        tk.Label(free_row, text="Free space:", bg=c["bg"], fg=c["text"], font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(free_row, text=human_size(data["free"]), bg=c["bg"], fg=c["success"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)

    # -- LARGE FILES TAB -------------------------------------------------------

    def _build_large_files_tab(self, parent):
        c = self.colors
        top = tk.Frame(parent, bg=c["bg"])
        top.pack(fill="x", padx=8, pady=8)

        tk.Label(top, text="Folder:", bg=c["bg"], fg=c["text"], font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        self.large_path_var = tk.StringVar(value=os.environ.get("USERPROFILE", os.path.expanduser("~")))
        path_entry = tk.Entry(top, textvariable=self.large_path_var, width=48)
        path_entry.grid(row=0, column=1, padx=6)

        browse_btn = tk.Button(top, text="Browse...", command=self.browse_large_files_folder,
                                bg="#616161", fg="white", relief="flat", padx=8, pady=3)
        browse_btn.grid(row=0, column=2, padx=4)

        tk.Label(top, text="Min size (MB):", bg=c["bg"], fg=c["text"], font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.large_min_mb_var = tk.StringVar(value="100")
        min_size_entry = tk.Entry(top, textvariable=self.large_min_mb_var, width=8)
        min_size_entry.grid(row=1, column=1, sticky="w", pady=(8, 0))

        btn_row = tk.Frame(parent, bg=c["bg"])
        btn_row.pack(fill="x", padx=8)

        self.large_scan_btn = tk.Button(
            btn_row, text="🔍 Scan for Large Files", command=self.start_large_file_scan,
            bg=c["primary"], fg="white", relief="flat", padx=12, pady=6, cursor="hand2"
        )
        self.large_scan_btn.pack(side="left")

        self.large_stop_btn = tk.Button(
            btn_row, text="⏹ Stop", command=self.stop_large_file_scan,
            bg=c["danger"], fg="white", relief="flat", padx=12, pady=6, state="disabled"
        )
        self.large_stop_btn.pack(side="left", padx=6)

        self.large_delete_btn = tk.Button(
            btn_row, text="🗑 Delete Selected", command=self.delete_selected_large_files,
            bg="#616161", fg="white", relief="flat", padx=12, pady=6, state="disabled"
        )
        self.large_delete_btn.pack(side="left", padx=6)

        self.large_status_label = tk.Label(btn_row, text="", bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9))
        self.large_status_label.pack(side="left", padx=10)

        tree_frame = tk.Frame(parent, bg=c["bg"])
        tree_frame.pack(fill="both", expand=True, padx=8, pady=8)

        columns = ("size", "path")
        self.large_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.large_tree.heading("size", text="Size")
        self.large_tree.heading("path", text="Path")
        self.large_tree.column("size", width=90, anchor="e")
        self.large_tree.column("path", width=560, anchor="w")
        self.large_tree.pack(side="left", fill="both", expand=True)

        tree_scroll = tk.Scrollbar(tree_frame, command=self.large_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.large_tree.configure(yscrollcommand=tree_scroll.set)

    def browse_large_files_folder(self):
        folder = filedialog.askdirectory(initialdir=self.large_path_var.get())
        if folder:
            self.large_path_var.set(folder)

    def start_large_file_scan(self):
        try:
            min_mb = float(self.large_min_mb_var.get())
        except ValueError:
            messagebox.showerror("Invalid Size", "Please enter a numeric size in MB.")
            return

        path = self.large_path_var.get()
        if not os.path.exists(path):
            messagebox.showerror("Folder Not Found", f"Could not find:\n{path}")
            return

        self.large_scan_stop.clear()
        self.large_scan_btn.config(state="disabled")
        self.large_stop_btn.config(state="normal")
        self.large_delete_btn.config(state="disabled")
        self.large_status_label.config(text="Scanning...")
        for row in self.large_tree.get_children():
            self.large_tree.delete(row)

        min_bytes = int(min_mb * 1024 * 1024)
        thread = threading.Thread(target=self._large_scan_worker, args=(path, min_bytes), daemon=True)
        thread.start()

    def stop_large_file_scan(self):
        self.large_scan_stop.set()
        self.large_status_label.config(text="Stopping...")

    def _large_scan_worker(self, path, min_bytes):
        results = find_large_files(path, min_bytes, stop_flag=self.large_scan_stop)
        self.root.after(0, lambda: self._on_large_scan_done(results))

    def _on_large_scan_done(self, results):
        self.large_files_results = results
        for path, size in results:
            self.large_tree.insert("", "end", values=(human_size(size), path))
        self.large_scan_btn.config(state="normal")
        self.large_stop_btn.config(state="disabled")
        self.large_delete_btn.config(state="normal" if results else "disabled")
        self.large_status_label.config(text=f"Found {len(results)} file(s)")

    def delete_selected_large_files(self):
        selected_items = self.large_tree.selection()
        if not selected_items:
            messagebox.showinfo("Nothing Selected", "Select one or more files to delete first.")
            return

        paths = [self.large_tree.item(item, "values")[1] for item in selected_items]
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Permanently delete {len(paths)} file(s)? This cannot be undone."
        )
        if not confirm:
            return

        freed = 0
        errors = 0
        for item, path in zip(selected_items, paths):
            size = get_file_size(path)
            ok, err = delete_file_safe(path)
            if ok:
                freed += size
                self.large_tree.delete(item)
            else:
                errors += 1

        self.large_delete_btn.config(state="normal" if self.large_tree.get_children() else "disabled")
        msg = f"Freed {human_size(freed)}."
        if errors:
            msg += f" {errors} file(s) could not be deleted (in use or access denied)."
        self.large_status_label.config(text=msg)
        messagebox.showinfo("Delete Complete", msg)

    # -- STARTUP MANAGER TAB ----------------------------------------------------

    def _build_startup_tab(self, parent):
        c = self.colors

        note = tk.Label(
            parent,
            text="Programs registered to launch at sign-in (Run registry keys). "
                 "Disabling an entry backs it up so it can be re-enabled anytime; "
                 "it does not uninstall the program.",
            bg=c["bg"], fg=c["muted"], font=("Segoe UI", 8), wraplength=720, justify="left"
        )
        note.pack(fill="x", padx=8, pady=(8, 4))

        btn_row = tk.Frame(parent, bg=c["bg"])
        btn_row.pack(fill="x", padx=8)

        tk.Button(btn_row, text="🔄 Refresh", command=self.refresh_startup_lists,
                  bg=c["primary"], fg="white", relief="flat", padx=12, pady=6).pack(side="left")

        self.startup_status_label = tk.Label(btn_row, text="", bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9))
        self.startup_status_label.pack(side="left", padx=10)

        # Enabled items
        enabled_frame = tk.LabelFrame(parent, text="Currently Enabled", font=("Segoe UI", 10, "bold"),
                                       bg=c["panel_bg"], fg=c["primary"], padx=8, pady=6)
        enabled_frame.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        columns = ("name", "scope", "command")
        self.startup_tree = ttk.Treeview(enabled_frame, columns=columns, show="headings", height=8, selectmode="browse")
        self.startup_tree.heading("name", text="Name")
        self.startup_tree.heading("scope", text="Scope")
        self.startup_tree.heading("command", text="Command")
        self.startup_tree.column("name", width=160)
        self.startup_tree.column("scope", width=90, anchor="center")
        self.startup_tree.column("command", width=440)
        self.startup_tree.pack(fill="both", expand=True, side="left")

        enabled_scroll = tk.Scrollbar(enabled_frame, command=self.startup_tree.yview)
        enabled_scroll.pack(side="right", fill="y")
        self.startup_tree.configure(yscrollcommand=enabled_scroll.set)

        tk.Button(parent, text="🚫 Disable Selected", command=self.disable_selected_startup_item,
                  bg=c["warning"], fg="white", relief="flat", padx=12, pady=6).pack(padx=8, pady=(0, 8), anchor="w")

        # Disabled items
        disabled_frame = tk.LabelFrame(parent, text="Disabled by TempCleaner Pro", font=("Segoe UI", 10, "bold"),
                                        bg=c["panel_bg"], fg=c["primary"], padx=8, pady=6)
        disabled_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self.startup_disabled_tree = ttk.Treeview(disabled_frame, columns=("name", "command"), show="headings", height=5)
        self.startup_disabled_tree.heading("name", text="Name")
        self.startup_disabled_tree.heading("command", text="Command")
        self.startup_disabled_tree.column("name", width=160)
        self.startup_disabled_tree.column("command", width=500)
        self.startup_disabled_tree.pack(fill="both", expand=True, side="left")

        disabled_scroll = tk.Scrollbar(disabled_frame, command=self.startup_disabled_tree.yview)
        disabled_scroll.pack(side="right", fill="y")
        self.startup_disabled_tree.configure(yscrollcommand=disabled_scroll.set)

        tk.Button(parent, text="✅ Re-enable Selected", command=self.enable_selected_startup_item,
                  bg=c["success"], fg="white", relief="flat", padx=12, pady=6).pack(padx=8, pady=(0, 8), anchor="w")

        self.refresh_startup_lists()

    def refresh_startup_lists(self):
        for row in self.startup_tree.get_children():
            self.startup_tree.delete(row)
        for row in self.startup_disabled_tree.get_children():
            self.startup_disabled_tree.delete(row)

        if winreg is None:
            self.startup_status_label.config(text="Startup management requires Windows.")
            return

        enabled = list_startup_items()
        for item in enabled:
            self.startup_tree.insert("", "end", values=(item["name"], item["scope"], item["command"]))

        disabled = list_disabled_startup_items()
        for item in disabled:
            self.startup_disabled_tree.insert("", "end", values=(item["name"], item["command"]))

        self.startup_status_label.config(text=f"{len(enabled)} enabled, {len(disabled)} disabled")

    def disable_selected_startup_item(self):
        selection = self.startup_tree.selection()
        if not selection:
            messagebox.showinfo("Nothing Selected", "Select a startup item to disable first.")
            return
        name, scope, command = self.startup_tree.item(selection[0], "values")

        enabled_items = list_startup_items()
        match = next((i for i in enabled_items if i["name"] == name and i["scope"] == scope), None)
        if not match:
            messagebox.showerror("Not Found", "That item could no longer be found in the registry.")
            self.refresh_startup_lists()
            return

        if match["admin_needed"] and not is_admin():
            messagebox.showwarning("Admin Required", "Restart TempCleaner Pro as Administrator to change this entry.")
            return

        ok, err = disable_startup_item(match)
        if ok:
            self.refresh_startup_lists()
        else:
            messagebox.showerror("Could Not Disable", err or "Unknown error.")

    def enable_selected_startup_item(self):
        selection = self.startup_disabled_tree.selection()
        if not selection:
            messagebox.showinfo("Nothing Selected", "Select a disabled item to re-enable first.")
            return
        name = self.startup_disabled_tree.item(selection[0], "values")[0]
        ok, err = enable_startup_item(name)
        if ok:
            self.refresh_startup_lists()
        else:
            messagebox.showerror("Could Not Re-enable", err or "Unknown error.")

    # -- SCHEDULER TAB -----------------------------------------------------------

    def _build_schedule_tab(self, parent):
        c = self.colors

        note = tk.Label(
            parent,
            text="Set up automatic cleaning using the Windows Task Scheduler. "
                 "A scheduled run uses your current checkbox selections from the Clean tab "
                 "(only the items marked ✓ by default) and runs silently in the background.",
            bg=c["bg"], fg=c["muted"], font=("Segoe UI", 8), wraplength=720, justify="left"
        )
        note.pack(fill="x", padx=8, pady=8)

        form = tk.LabelFrame(parent, text="Schedule", font=("Segoe UI", 10, "bold"),
                              bg=c["panel_bg"], fg=c["primary"], padx=12, pady=12)
        form.pack(fill="x", padx=8, pady=8)

        self.schedule_freq_var = tk.StringVar(value="DAILY")
        for i, (label, value) in enumerate([
            ("Daily", "DAILY"), ("Weekly (Sunday)", "WEEKLY"), ("At each sign-in", "ONLOGON")
        ]):
            tk.Radiobutton(form, text=label, variable=self.schedule_freq_var, value=value,
                           bg=c["panel_bg"], fg=c["text"], selectcolor=c["panel_bg"],
                           font=("Segoe UI", 9)).grid(row=0, column=i, sticky="w", padx=(0, 16))

        tk.Label(form, text="Time (24h):", bg=c["panel_bg"], fg=c["text"],
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(10, 0))
        time_row = tk.Frame(form, bg=c["panel_bg"])
        time_row.grid(row=1, column=1, columnspan=2, sticky="w", pady=(10, 0))

        self.schedule_hour_var = tk.StringVar(value="02")
        self.schedule_minute_var = tk.StringVar(value="00")
        hour_spin = tk.Spinbox(time_row, from_=0, to=23, width=3, format="%02.0f", textvariable=self.schedule_hour_var)
        hour_spin.pack(side="left")
        tk.Label(time_row, text=":", bg=c["panel_bg"], fg=c["text"]).pack(side="left")
        minute_spin = tk.Spinbox(time_row, from_=0, to=59, width=3, format="%02.0f", textvariable=self.schedule_minute_var)
        minute_spin.pack(side="left")

        btn_row = tk.Frame(parent, bg=c["bg"])
        btn_row.pack(fill="x", padx=8, pady=8)

        tk.Button(btn_row, text="✅ Enable Scheduled Cleaning", command=self.enable_schedule,
                  bg=c["success"], fg="white", relief="flat", padx=12, pady=6).pack(side="left")
        tk.Button(btn_row, text="🚫 Disable Scheduled Cleaning", command=self.disable_schedule,
                  bg=c["danger"], fg="white", relief="flat", padx=12, pady=6).pack(side="left", padx=8)

        self.schedule_status_label = tk.Label(parent, text="", bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9))
        self.schedule_status_label.pack(anchor="w", padx=8)

        self.refresh_schedule_status()

    def refresh_schedule_status(self):
        if scheduled_task_exists():
            self.schedule_status_label.config(text="✓ A scheduled cleaning task is currently active.", fg=self.colors["success"])
        else:
            self.schedule_status_label.config(text="No scheduled cleaning task is currently set up.", fg=self.colors["muted"])

    def enable_schedule(self):
        freq = self.schedule_freq_var.get()
        time_str = f"{int(self.schedule_hour_var.get()):02d}:{int(self.schedule_minute_var.get()):02d}"
        ok, msg = create_scheduled_task(freq, time_str)
        if ok:
            messagebox.showinfo("Scheduled", msg)
        else:
            messagebox.showerror("Could Not Schedule", msg)
        self.refresh_schedule_status()

    def disable_schedule(self):
        ok, msg = delete_scheduled_task()
        if ok:
            messagebox.showinfo("Removed", msg)
        else:
            messagebox.showwarning("Notice", msg)
        self.refresh_schedule_status()

    # -- REPORTS TAB -------------------------------------------------------------

    def _build_reports_tab(self, parent):
        c = self.colors

        top = tk.Frame(parent, bg=c["bg"])
        top.pack(fill="x", padx=8, pady=8)
        tk.Button(top, text="🔄 Refresh", command=self.refresh_reports_list,
                  bg=c["primary"], fg="white", relief="flat", padx=12, pady=6).pack(side="left")
        tk.Button(top, text="📂 Open Reports Folder", command=self.open_reports_folder,
                  bg="#616161", fg="white", relief="flat", padx=12, pady=6).pack(side="left", padx=6)

        body = tk.Frame(parent, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        list_frame = tk.Frame(body, bg=c["bg"])
        list_frame.pack(side="left", fill="y")

        self.reports_listbox = tk.Listbox(list_frame, width=32, height=22, font=("Segoe UI", 9))
        self.reports_listbox.pack(side="left", fill="y")
        self.reports_listbox.bind("<<ListboxSelect>>", self.on_report_selected)

        list_scroll = tk.Scrollbar(list_frame, command=self.reports_listbox.yview)
        list_scroll.pack(side="left", fill="y")
        self.reports_listbox.configure(yscrollcommand=list_scroll.set)

        self.report_text_box = tk.Text(body, font=("Consolas", 9), bg=c["panel_bg"], fg=c["text"],
                                        state="disabled", relief="flat", bd=1)
        self.report_text_box.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self._report_paths = []
        self.refresh_reports_list()

    def refresh_reports_list(self):
        self.reports_listbox.delete(0, "end")
        self._report_paths = list_saved_reports()
        for path in self._report_paths:
            self.reports_listbox.insert("end", os.path.basename(path))

    def on_report_selected(self, event=None):
        selection = self.reports_listbox.curselection()
        if not selection:
            return
        path = self._report_paths[selection[0]]
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            content = f"Could not open report: {e}"

        self.report_text_box.config(state="normal")
        self.report_text_box.delete("1.0", "end")
        self.report_text_box.insert("1.0", content)
        self.report_text_box.config(state="disabled")

    def open_reports_folder(self):
        path = get_reports_dir()
        try:
            os.startfile(path)  # Windows only
        except AttributeError:
            messagebox.showinfo("Reports Folder", path)
        except OSError as e:
            messagebox.showerror("Could Not Open Folder", str(e))


def main():
    if "--auto-clean" in sys.argv:
        # Silent mode for the scheduled task: no GUI, just clean and log a report.
        run_silent_clean()
        return

    if os.name != "nt":
        messagebox.showerror("Error", "This tool is for Windows only.")
        sys.exit(1)

    config = load_config()
    if not prompt_login(config):
        sys.exit(0)

    root = tk.Tk()
    TempCleanerApp(root, config)
    root.mainloop()


if __name__ == "__main__":
    main()
