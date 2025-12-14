import os
import json
import time
import requests
import schedule
from datetime import datetime, timezone

# --- CONFIGURATION ---
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", os.path.abspath("CYRIDE_DATA"))
FILE_SAVE_DIRECTORY = os.path.join(BASE_DIR, "Location")
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")
API_KEY = "f4c90d45c2dc2b1e2c51dc70830937147195747315d45f0e942fce688c353165"
BASE_URL = "https://api.syncromatics.com/portal"

# Route Definitions
ROUTES = [
    {"color":"#DA1F3D","id":4528,"name":"1 Red West"},
    {"color":"#DA1F3D","id":4529,"name":"1 Red East"},
    {"color":"#008A4B","id":4530,"name":"2 Green West"},
    {"color":"#008A4B","id":4531,"name":"2 Green East"},
    {"color":"#1989CA","id":4532,"name":"3 Blue"},
    {"color":"#FFCC00","id":4533,"name":"5 Yellow"},
    {"color":"#996633","id":4534,"name":"6 Brown South"},
    {"color":"#996633","id":4535,"name":"6 Brown North"},
    {"color":"#6C55A3","id":4536,"name":"7 Purple"},
    {"color":"#1FB7DA","id":4537,"name":"8 Aqua"},
    {"color":"#A74888","id":4538,"name":"9 Plum"},
    {"color":"#FF4422","id":4539,"name":"11 Cherry"},
    {"color":"#FF9966","id":4540,"name":"14 Peach"},
    {"color":"#F87600","id":4541,"name":"23 Orange"},
    {"color":"#CCA02F","id":4542,"name":"25 Gold South"},
    {"color":"#CCA02F","id":4543,"name":"25 Gold North"},
    {"color":"#AA2244","id":4570,"name":"21 Cardinal"},
    {"color":"#9688B6","id":4571,"name":"12 Lilac"},
    {"color":"#446688","id":4572,"name":"Moonlight Express A West"},
    {"color":"#446688","id":4573,"name":"Moonlight Express A East"},
    {"color":"#446688","id":4574,"name":"Moonlight Express B"}
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def wait_for_mount():
    log(f"Checking for mount at: {BASE_DIR}")
    while True:
        if os.path.ismount(BASE_DIR) or os.path.exists(MOUNT_DIR):
            log("Mount detected. Logging started.")
            break
        log("Waiting for Google Drive to mount...")
        time.sleep(10)

def get_cardinal_direction(heading_degrees):
    if heading_degrees is None: return "N/A"
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    try:
        idx = round(float(heading_degrees) / 45) % 8
        return directions[idx]
    except (ValueError, TypeError):
        return "N/A"

def fetch_all_vehicle_data():
    try:
        vehicles_res = requests.get(f"{BASE_URL}/vehicles?api-key={API_KEY}", timeout=10)
        all_vehicles = vehicles_res.json() if vehicles_res.ok else []
        
        vehicles_by_id = {v['id']: v for v in all_vehicles}
        
        # Enrich with route info
        for route in ROUTES:
            try:
                res = requests.get(f"{BASE_URL}/routes/{route['id']}/vehicles?api-key={API_KEY}", timeout=3)
                if res.ok:
                    for v in res.json():
                        if v['id'] in vehicles_by_id:
                            vehicles_by_id[v['id']].update({'routeName': route['name'], 'routeColor': route['color']})
            except: pass

        # Return ALL vehicles found (No time filtering)
        return list(vehicles_by_id.values())
        
    except Exception as e:
        log(f"API Error: {e}")
        return None

def save_periodic_data():
    vehicles = fetch_all_vehicle_data()
    if vehicles is None: return

    now = datetime.now()
    output_data = {
        "Vehicles": []
    }

    for v in vehicles:
        # Check for valid lat/lon before saving, but ignore time
        if v.get('lat') is None or v.get('lon') is None:
            continue

        r_name = v.get('routeName')
        if not r_name:
            r_name = "Out Of Service"
            if not v.get('routeColor'):
                v['routeColor'] = "#808080"

        formatted_vehicle = {
            "name": v.get('name', 'Unknown'),
            "lat": v.get('lat'),
            "lon": v.get('lon'),
            "heading": get_cardinal_direction(v.get('headingDegrees')),
            "headingDegrees": v.get('headingDegrees', 0),
            "speed": v.get('speed', 0),
            "passengerPercent": v.get('passengerLoad', 0),
            "routeName": r_name,
            "routeColor": v.get('routeColor', '#808080'),
            "lastUpdated": v.get('lastUpdated')
        }
        output_data["Vehicles"].append(formatted_vehicle)

    # NEW STRUCTURE: YYYY/MM/DD/HH/MM/SS.json
    save_path = os.path.join(
        FILE_SAVE_DIRECTORY, 
        now.strftime('%Y'), 
        now.strftime('%m'), 
        now.strftime('%d'),
        now.strftime('%H'),
        now.strftime('%M')
    )
    
    try:
        os.makedirs(save_path, exist_ok=True)
        full_file_path = os.path.join(save_path, now.strftime('%S.json'))
        
        with open(full_file_path, 'w') as f:
            json.dump(output_data, f, indent=4)
        
        log(f"Saved {len(output_data['Vehicles'])} vehicles to {now.strftime('%H:%M:%S')}")
    except Exception as e:
        log(f"Write Error: {e}")

if __name__ == '__main__':
    log("--- CyMap Logger Starting ---")
    wait_for_mount()
    os.makedirs(FILE_SAVE_DIRECTORY, exist_ok=True)
    schedule.every(5).seconds.do(save_periodic_data)
    while True:
        schedule.run_pending()
        time.sleep(1)
