import os
import json
import time
import requests
import schedule
from datetime import datetime, timezone

BASE_DIR = os.getenv("CYRIDE_BASE_DIR", os.path.abspath("CYRIDE_DATA"))
FILE_SAVE_DIRECTORY = os.path.join(BASE_DIR, "Location")
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")
API_KEY = "f4c90d45c2dc2b1e2c51dc70830937147195747315d45f0e942fce688c353165"
BASE_URL = "https://api.syncromatics.com/portal"

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def wait_for_mount():
    """Blocks until drive is mounted."""
    log(f"Checking for mount at: {BASE_DIR}")
    while True:
        if os.path.ismount(BASE_DIR) or os.path.exists(MOUNT_DIR):
            log("Mount detected. Logging started.")
            break
        log("Waiting for Google Drive to mount...")
        time.sleep(10)

def fetch_and_save():
    try:
        vehicles_res = requests.get(f"{BASE_URL}/vehicles?api-key={API_KEY}", timeout=10)
        if not vehicles_res.ok: return
        vehicles = vehicles_res.json()
        
        now = datetime.now()
        output_data = {
            "Vehicles": [{
                "name": v.get('name', 'Unknown'),
                "lat": v.get('lat'),
                "lon": v.get('lon'),
                "headingDegrees": v.get('headingDegrees', 0),
                "speed": v.get('speed', 0)
            } for v in vehicles]
        }
        
        save_path = os.path.join(FILE_SAVE_DIRECTORY, now.strftime('%Y'), now.strftime('%m'), now.strftime('%d'))
        os.makedirs(save_path, exist_ok=True)
        with open(os.path.join(save_path, now.strftime('%H-%M-%S.json')), 'w') as f:
            json.dump(output_data, f, indent=4)
        log(f"Saved {len(vehicles)} vehicles.")
    except Exception as e:
        log(f"Error: {e}")

if __name__ == '__main__':
    log("--- CyMap Logger Starting ---")
    
    # CRITICAL: Wait for mount
    wait_for_mount()
    
    os.makedirs(FILE_SAVE_DIRECTORY, exist_ok=True)
    schedule.every(5).seconds.do(fetch_and_save)
    while True:
        schedule.run_pending()
        time.sleep(1)
