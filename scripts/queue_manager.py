import os
import sys
import time
import json
import argparse
import hashlib
from datetime import datetime, timedelta

# --- CONFIGURATION ---
# Base directory defaults to ~/CYRIDE if env var not set
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", "/home/sdr/CYRIDE")

# Directory Definitions
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")
STATE_DIR = os.path.join(BASE_DIR, "states")
QUEUE_FILE = os.path.join(BASE_DIR, "queue.lst")

# Subfolders to scan
GROUPS = ["CYRIDE-CIRC", "CYRIDE-FIXED"]

def log(msg):
    """Prints message with timestamp and flushes stdout immediately."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def wait_for_drive():
    """Pauses execution until the Google Drive mount (or specific folder) is detected."""
    # We check for MOUNT_DIR because it's the specific target for scanning.
    # If the drive isn't mounted, this folder likely won't exist or will be empty/different.
    while not os.path.exists(MOUNT_DIR):
        log(f"Waiting for GDrive mount at: {MOUNT_DIR}...")
        time.sleep(10)
    log("GDrive mount detected. Resuming startup.")

def check_permissions():
    """Checks if we can write to the necessary directories."""
    log(f"Checking permissions for {STATE_DIR}...")
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        test_file = os.path.join(STATE_DIR, ".perm_test")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        log("SUCCESS: Write permission confirmed for States directory.")
    except Exception as e:
        log(f"CRITICAL ERROR: Cannot write to {STATE_DIR}. Reason: {e}")
        log(f"HINT: Run 'sudo chown -R $USER {BASE_DIR}' or check service user.")
        sys.exit(1)

def get_file_hash(filepath):
    """Calculates MD5 hash of a file."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        log(f"Error hashing {filepath}: {e}")
        return None

def get_state_file_path(date_obj):
    """Returns path: STATE_DIR/YYYY/MM/DD.json"""
    return os.path.join(
        STATE_DIR,
        date_obj.strftime('%Y'),
        date_obj.strftime('%m'),
        f"{date_obj.strftime('%d')}.json"
    )

def load_state(date_obj):
    filepath = get_state_file_path(date_obj)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            log(f"Warning: Corrupt state file {filepath}")
    return {}

def save_state(date_obj, state_data):
    filepath = get_state_file_path(date_obj)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, 'w') as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        log(f"Error saving state {filepath}: {e}")

def append_to_queue(items):
    """Appends unique items to the queue.lst file."""
    if not items:
        return

    existing_in_queue = set()
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, 'r') as f:
                for line in f:
                    clean = line.strip().replace(';', '')
                    if clean and clean != "END":
                        existing_in_queue.add(clean)
        except Exception:
            pass
    
    try:
        count = 0
        with open(QUEUE_FILE, 'a') as f:
            for item in items:
                if item not in existing_in_queue:
                    f.write(f"{item};\n")
                    count += 1
            f.write("END;\n")
        
        if count > 0:
            log(f"Queued {count} new files.")
    except Exception as e:
        log(f"Error writing to queue file: {e}")

def scan_date(date_obj):
    """Scans for files on a specific day."""
    state_data = load_state(date_obj)
    state_changed = False
    new_queue_items = []
    
    current_time_str = datetime.now().isoformat()
    
    year_str = date_obj.strftime('%Y')
    month_strs = [date_obj.strftime('%m'), str(date_obj.month)]
    day_strs = [date_obj.strftime('%d'), str(date_obj.day)]
    
    path_suffixes = []
    for m in dict.fromkeys(month_strs): 
        for d in dict.fromkeys(day_strs):
            path_suffixes.append(os.path.join(year_str, m, d))

    for group in GROUPS:
        for suffix in path_suffixes:
            day_path = os.path.join(MOUNT_DIR, group, suffix)
            
            if not os.path.exists(day_path):
                continue
                
            try:
                files = sorted([f for f in os.listdir(day_path) if f.endswith(".mp3")])
                
                for f in files:
                    full_path = os.path.join(day_path, f)
                    
                    if full_path not in state_data:
                        log(f"Found New File: {f}")
                        
                        file_hash = get_file_hash(full_path)
                        state_data[full_path] = {
                            "Path": full_path,
                            "Hash": file_hash,
                            "status": "queue",
                            "TimeAdded": current_time_str,
                            "TimeUpdated": current_time_str
                        }
                        
                        new_queue_items.append(full_path)
                        state_changed = True
                        
            except OSError as e:
                log(f"Error accessing {day_path}: {e}")

    if state_changed:
        save_state(date_obj, state_data)
        if new_queue_items:
            append_to_queue(new_queue_items)

def main():
    parser = argparse.ArgumentParser(description="CyRide Queue Manager")
    parser.add_argument("--backlog", type=int, help="Number of past days to scan")
    args = parser.parse_args()

    log(f"--- Queue Manager Starting ---")
    log(f"Base Directory: {BASE_DIR}")
    
    # Check for drive mount BEFORE doing anything else
    wait_for_drive()
    
    # Now safe to check write permissions
    check_permissions()

    if args.backlog:
        log(f"Mode: BACKLOG SCAN ({args.backlog} days)")
        for i in range(args.backlog + 1):
            scan_d = datetime.now() - timedelta(days=i)
            scan_date(scan_d)
        log("--- Backlog Scan Complete ---")
    else:
        log("Mode: LIVE MONITORING")
        while True:
            try:
                scan_date(datetime.now())
            except KeyboardInterrupt:
                break
            except Exception as e:
                log(f"Loop Error: {e}")
            
            time.sleep(5)

if __name__ == "__main__":
    main()
