import os
import time
import json
from datetime import datetime

# --- CONFIG ---
MOUNT_DIR = "/home/sdr/CYRIDE/SDR Recordings"
QUEUE_FILE = "/home/sdr/scripts/queue.lst"
STATE_DIR = "/home/sdr/CYRIDE/states"
GROUPS = ["CYRIDE-CIRC", "CYRIDE-FIXED"]

# Ensure state directory exists
if not os.path.exists(STATE_DIR): os.makedirs(STATE_DIR)

def get_state_file(date_str):
    return os.path.join(STATE_DIR, f"{date_str}.json")

def load_state(date_str):
    filepath = get_state_file(date_str)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f: return json.load(f)
        except: pass
    return {}

def save_state(date_str, state_data):
    filepath = get_state_file(date_str)
    try:
        with open(filepath, 'w') as f: json.dump(state_data, f, indent=2)
    except: pass

def append_to_queue(items):
    if not items: return
    existing = set()
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, 'r') as f:
            for line in f:
                if line.strip() and line.strip() != "END;":
                    existing.add(line.strip().replace(';', ''))
    
    with open(QUEUE_FILE, 'a') as f:
        for item in items:
            if item not in existing:
                f.write(f"{item};\n")
        f.write("END;\n")

# --- MAIN LOOP ---
print("--- Queue Manager Started (Live Watcher) ---")

while True:
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    state_data = load_state(date_str)
    state_changed = False
    new_files = []

    # Check Today's Folders
    for group in GROUPS:
        # Path: MOUNT_DIR/Group/YYYY/MM/DD
        day_path = os.path.join(MOUNT_DIR, group, now.strftime('%Y'), now.strftime('%m'), now.strftime('%d'))
        
        if not os.path.exists(day_path): continue

        try:
            # We assume files with modification time > startup time are new, 
            # OR files that simply aren't in the state file yet.
            files = [f for f in os.listdir(day_path) if f.endswith(".mp3")]
            
            for f in files:
                full_path = os.path.join(day_path, f)
                
                if full_path not in state_data:
                    print(f"New Live File: {f}")
                    state_data[full_path] = {
                        "status": "queue",
                        "timestamp": time.time()
                    }
                    new_files.append(full_path)
                    state_changed = True
        except OSError: pass

    if state_changed:
        save_state(date_str, state_data)
    
    if new_files:
        append_to_queue(new_files)

    time.sleep(2) # Check frequently for live updates
