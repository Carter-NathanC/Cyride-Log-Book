import os
import sys
import time
import json
import argparse
import hashlib
import tempfile
from datetime import datetime, timedelta

BASE_DIR = os.getenv("CYRIDE_BASE_DIR", os.path.abspath("CYRIDE_DATA"))
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")
STATE_DIR = os.path.join(BASE_DIR, "states")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
GROUPS = ["CYRIDE-CIRC", "CYRIDE-FIXED"]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def wait_for_mount():
    while not os.path.exists(MOUNT_DIR):
        log(f"Waiting for Audio Directory at: {MOUNT_DIR}...")
        time.sleep(10)

def load_state(date_obj):
    path = os.path.join(STATE_DIR, date_obj.strftime('%Y'), date_obj.strftime('%m'), f"{date_obj.strftime('%d')}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f: return json.load(f)
        except Exception as e:
            # CRITICAL FIX: If load fails (race condition), return None.
            # Do NOT return {}. Returning {} causes the script to think 
            # all files are new and resets them to 'queue'.
            log(f"Read Error on {path}: {e}. Skipping cycle.")
            return None
    return {}

def load_transcriptions(date_obj):
    path = os.path.join(TRANSCRIPT_DIR, date_obj.strftime('%Y'), date_obj.strftime('%m'), f"{date_obj.strftime('%d')}.json")
    processed_paths = set()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                for entry in data:
                    if "Path" in entry:
                        processed_paths.add(entry["Path"])
        except Exception:
            pass
    return processed_paths

def save_state(date_obj, state_data):
    path = os.path.join(STATE_DIR, date_obj.strftime('%Y'), date_obj.strftime('%m'), f"{date_obj.strftime('%d')}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    # ATOMIC WRITE FIX: Write to temp, then rename. 
    # Prevents readers from seeing a half-written empty file.
    dir_name = os.path.dirname(path)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False) as tf:
        json.dump(state_data, tf, indent=4)
        tempname = tf.name
    
    try:
        os.replace(tempname, path)
    except Exception as e:
        log(f"Save Error: {e}")
        if os.path.exists(tempname): os.remove(tempname)

def scan_date(date_obj):
    state_data = load_state(date_obj)
    
    # Safety Check: If state read failed, STOP. Do not overwrite.
    if state_data is None: return

    processed_files = load_transcriptions(date_obj)
    state_changed = False
    current_time_str = datetime.now().isoformat()
    year_str = date_obj.strftime('%Y')
    
    paths_to_check = []
    for g in GROUPS:
        for m in {date_obj.strftime('%m'), str(date_obj.month)}:
            for d in {date_obj.strftime('%d'), str(date_obj.day)}:
                paths_to_check.append(os.path.join(MOUNT_DIR, g, year_str, m, d))

    for day_path in paths_to_check:
        if not os.path.exists(day_path): continue
        try:
            files = sorted([f for f in os.listdir(day_path) if f.endswith(".mp3")])
            for f in files:
                full_path = os.path.join(day_path, f)
                if full_path not in state_data:
                    log(f"Found New File: {f}")
                    
                    status = "queue"
                    if full_path in processed_files:
                        status = "processed"
                        log(f"  -> Already in transcriptions. Marking processed.")

                    state_data[full_path] = {
                        "Path": full_path,
                        "status": status,
                        "TimeAdded": current_time_str
                    }
                    state_changed = True
        except OSError: pass

    if state_changed:
        save_state(date_obj, state_data)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog", type=int, help="Days to scan back")
    args = parser.parse_args()

    log(f"--- Queue Manager Starting ---")
    wait_for_mount()
    os.makedirs(STATE_DIR, exist_ok=True)

    if args.backlog:
        log(f"Mode: BACKLOG SCAN ({args.backlog} days)")
        for i in range(args.backlog + 1):
            scan_date(datetime.now() - timedelta(days=i))
    else:
        log("Mode: LIVE MONITORING")
        while True:
            try:
                scan_date(datetime.now())
            except KeyboardInterrupt: break
            except Exception as e: log(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
