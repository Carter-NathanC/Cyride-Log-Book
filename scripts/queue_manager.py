import os
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
QUEUE_FILE = os.path.join(BASE_DIR, "queue.lst")  # File where queue paths are written for other apps

# Subfolders to scan
GROUPS = ["CYRIDE-CIRC", "CYRIDE-FIXED"]

def get_file_hash(filepath):
    """Calculates MD5 hash of a file to ensure uniqueness."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            # Read in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error hashing {filepath}: {e}")
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
    """Loads the state JSON for a specific date."""
    filepath = get_state_file_path(date_obj)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Corrupt state file {filepath}")
    return {}

def save_state(date_obj, state_data):
    """Saves the state JSON for a specific date."""
    filepath = get_state_file_path(date_obj)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, 'w') as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        print(f"Error saving state {filepath}: {e}")

def append_to_queue(items):
    """Appends unique items to the legacy queue.lst file."""
    if not items:
        return

    # Read existing to avoid duplicates in the text file
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
        with open(QUEUE_FILE, 'a') as f:
            for item in items:
                if item not in existing_in_queue:
                    f.write(f"{item};\n")
            # We add a marker line if needed, or just list files. 
            # Based on your prompt, just adding files.
            f.write("END;\n")
        print(f"Appended {len(items)} items to {QUEUE_FILE}")
    except Exception as e:
        print(f"Error writing to queue file: {e}")

def scan_date(date_obj):
    """Scans for files on a specific day and updates state."""
    state_data = load_state(date_obj)
    state_changed = False
    new_queue_items = []
    
    current_time_str = datetime.now().isoformat()
    
    # We scan both CIRC and FIXED folders
    for group in GROUPS:
        # Path construction: MOUNT_DIR/Group/YYYY/MM/DD
        day_path = os.path.join(
            MOUNT_DIR, 
            group, 
            date_obj.strftime('%Y'), 
            date_obj.strftime('%m'), 
            date_obj.strftime('%d')
        )
        
        if not os.path.exists(day_path):
            continue

        try:
            # List all mp3 files
            files = sorted([f for f in os.listdir(day_path) if f.endswith(".mp3")])
            
            for f in files:
                full_path = os.path.join(day_path, f)
                
                # If file is NOT in the JSON state, we process it
                if full_path not in state_data:
                    print(f"New File Found: {full_path}")
                    
                    file_hash = get_file_hash(full_path)
                    
                    # Create the entry with the requested structure
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
            print(f"Error accessing {day_path}: {e}")

    # Save changes if any
    if state_changed:
        save_state(date_obj, state_data)
        
        # Add to the text based queue file for other processors
        if new_queue_items:
            append_to_queue(new_queue_items)

def main():
    parser = argparse.ArgumentParser(description="CyRide Queue Manager & Scanner")
    parser.add_argument("--backlog", type=int, help="Number of past days to scan")
    args = parser.parse_args()

    print(f"--- CyRide Queue Manager Started ---")
    print(f"Base Directory: {BASE_DIR}")

    if args.backlog:
        # --- BACKLOG MODE ---
        print(f"Mode: BACKLOG SCAN ({args.backlog} days)")
        for i in range(args.backlog + 1):
            scan_d = datetime.now() - timedelta(days=i)
            print(f"Scanning date: {scan_d.strftime('%Y-%m-%d')}")
            scan_date(scan_d)
        print("--- Backlog Scan Complete ---")
    else:
        # --- LIVE MODE ---
        print("Mode: LIVE MONITORING")
        while True:
            try:
                # Always scan today's folder
                scan_date(datetime.now())
            except Exception as e:
                print(f"Critical Loop Error: {e}")
            
            # Sleep for 5 seconds before checking again
            time.sleep(5)

if __name__ == "__main__":
    main()
