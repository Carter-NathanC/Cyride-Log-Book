import os
import json
import time
import requests
import schedule
from datetime import datetime, timezone

# --- CONFIGURATION ---
# We use an environment variable for the base path if available, otherwise default.
# This makes it portable.
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", "/home/sdr/CYRIDE")
FILE_SAVE_DIRECTORY = os.path.join(BASE_DIR, "Location")

API_KEY = "f4c90d45c2dc2b1e2c51dc70830937147195747315d45f0e942fce688c353165"
BASE_URL = "https://api.syncromatics.com/portal"

# API Endpoints
ALL_VEHICLES_URL = f"{BASE_URL}/vehicles?api-key={API_KEY}"
DRIVERS_URL = f"{BASE_URL}/drivers?api-key={API_KEY}"
ROUTES_BASE_URL = f"{BASE_URL}/routes/"

# Route Definitions (Truncated for brevity, full list is in your original)
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

# --- HELPER FUNCTIONS ---

def get_cardinal_direction(heading_degrees):
    """Converts degrees (0-360) to NSEW string."""
    if heading_degrees is None: return "N/A"
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    try:
        idx = round(float(heading_degrees) / 45) % 8
        return directions[idx]
    except (ValueError, TypeError):
        return "N/A"

def fetch_route_vehicles(route):
    """Fetches vehicles for a specific route ID."""
    url = f"{ROUTES_BASE_URL}{route['id']}/vehicles?api-key={API_KEY}"
    try:
        res = requests.get(url, timeout=5)
        if res.ok: return route, res.json()
    except requests.RequestException:
        pass
    return route, []

def fetch_all_vehicle_data():
    """Fetches data from API and merges Route/Driver info."""
    try:
        # Fetch basic lists
        drivers_res = requests.get(DRIVERS_URL, timeout=10)
        vehicles_res = requests.get(ALL_VEHICLES_URL, timeout=10)
        
        drivers = drivers_res.json() if drivers_res.ok else []
        all_vehicles = vehicles_res.json() if vehicles_res.ok else []
        
        # Create lookup tables
        drivers_by_id = {d['id']: f"{d['firstName']} {d['lastName']}".strip() for d in drivers}
        vehicles_by_id = {v['id']: v for v in all_vehicles}
        
        # We process manually to avoid complexity of concurrent.futures inside this simple script
        # if performance is an issue, we can add it back, but simple loop is safer for "install anywhere"
        for route in ROUTES:
            r, v_list = fetch_route_vehicles(route)
            for vehicle in v_list:
                if vehicle['id'] in vehicles_by_id:
                    vehicles_by_id[vehicle['id']].update({
                        'routeName': route['name'], 
                        'routeColor': route['color']
                    })

        processed_vehicles = []
        # Filter for active vehicles (updated in last 24 hours)
        one_day_ago = datetime.now(timezone.utc).timestamp() - (24 * 3600)
        
        for vehicle in vehicles_by_id.values():
            if vehicle.get('lastUpdated') and vehicle.get('lat') and vehicle.get('lon'):
                try:
                    clean_ts = vehicle['lastUpdated'].replace('Z', '+00:00')
                    last_updated_ts = datetime.fromisoformat(clean_ts).timestamp()
                    
                    if last_updated_ts > one_day_ago:
                        vehicle['driverName'] = drivers_by_id.get(vehicle.get('driverId'), 'No Driver')
                        processed_vehicles.append(vehicle)
                except ValueError:
                    continue
                    
        return processed_vehicles
    except Exception as e:
        print(f"ERROR: API request failed: {e}")
        return None

def save_periodic_data():
    """Fetches and saves data."""
    vehicles = fetch_all_vehicle_data()
    if vehicles is None: return

    now = datetime.now()
    timestamp_filename = now.strftime('%H-%M-%S.json')
    
    formatted_vehicles_list = []
    
    for v in vehicles:
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
            "routeColor": v.get('routeColor', '#000000'),
            "lastUpdated": v.get('lastUpdated')
        }
        formatted_vehicles_list.append(formatted_vehicle)

    output_data = { "Vehicles": formatted_vehicles_list }

    save_path = os.path.join(
        FILE_SAVE_DIRECTORY, 
        now.strftime('%Y'), 
        now.strftime('%m'), 
        now.strftime('%d')
    )
    
    try:
        os.makedirs(save_path, exist_ok=True)
        full_file_path = os.path.join(save_path, timestamp_filename)
        
        with open(full_file_path, 'w') as f:
            json.dump(output_data, f, indent=4)
        
        print(f"[{now.strftime('%H:%M:%S')}] Success: Saved {len(formatted_vehicles_list)} vehicles.")
            
    except Exception as e:
        print(f"ERROR: Could not write file: {e}")

if __name__ == '__main__':
    print("\n" + "="*50 + "\n   Vehicle Location Logger\n" + "="*50)
    print(f"Target Directory: {FILE_SAVE_DIRECTORY}")
    
    if not os.path.exists(FILE_SAVE_DIRECTORY):
        try:
            os.makedirs(FILE_SAVE_DIRECTORY, exist_ok=True)
        except Exception as e:
            print(f"FATAL: Cannot create directory {FILE_SAVE_DIRECTORY}: {e}")
            exit(1)

    schedule.every(5).seconds.do(save_periodic_data)
    
    print("LOG: Service started. Loop 5s.")
    
    while True:
        schedule.run_pending()
        time.sleep(1)
