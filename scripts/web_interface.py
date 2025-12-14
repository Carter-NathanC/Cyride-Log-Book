import os
import sys
import json
import time
import glob
import re
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, send_file, jsonify, abort

# --- CONFIGURATION ---
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", "/home/sdr/CYRIDE")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
LOCATION_DIR = os.path.join(BASE_DIR, "Location")
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")

app = Flask(__name__)

# --- HELPERS ---

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def wait_for_drive():
    """Pauses execution until the Google Drive mount is detected."""
    while not os.path.exists(MOUNT_DIR):
        log(f"Waiting for GDrive mount at: {MOUNT_DIR}...")
        time.sleep(10)
    log("GDrive mount detected. Starting Web Server.")

def parse_filename_metadata(path):
    """
    Extracts time and Bus ID from filename.
    Format expected: hh_mm_ss-BusID.mp3 OR hh-mm-ss-BusID.mp3
    """
    basename = os.path.basename(path)
    match = re.search(r'(\d{2})[_-](\d{2})[_-](\d{2})-(\d+)\.mp3', basename)
    if match:
        h, m, s, bus_id = match.groups()
        return {
            "time_str": f"{h}:{m}:{s}",
            "seconds_of_day": int(h)*3600 + int(m)*60 + int(s),
            "bus_id": bus_id
        }
    return None

def find_closest_location(date_obj, target_seconds, bus_id):
    """
    Finds the location data for a specific bus at a specific time (±10s).
    """
    day_loc_dir = os.path.join(
        LOCATION_DIR, 
        date_obj.strftime('%Y'), 
        date_obj.strftime('%m'), 
        date_obj.strftime('%d')
    )
    
    if not os.path.exists(day_loc_dir):
        return None

    best_match = None
    found_vehicle_data = None
    
    # Check offsets: 0s, +1s, -1s ... up to ±10s
    search_offsets = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8, -8, 9, -9, 10, -10]

    for offset in search_offsets:
        check_sec = target_seconds + offset
        if check_sec < 0 or check_sec >= 86400: continue
        
        h = check_sec // 3600
        m = (check_sec % 3600) // 60
        s = check_sec % 60
        
        filename = f"{h:02d}-{m:02d}-{s:02d}.json"
        filepath = os.path.join(day_loc_dir, filename)
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    vehicles = data.get("Vehicles", [])
                    for v in vehicles:
                        if v.get("name") == bus_id:
                            found_vehicle_data = v
                            break
            except:
                continue
        
        if found_vehicle_data:
            break
            
    return found_vehicle_data

# --- ROUTES ---

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def get_data():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify([])
    
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify([])

    transcript_path = os.path.join(
        TRANSCRIPT_DIR,
        dt.strftime('%Y'),
        dt.strftime('%m'),
        dt.strftime('%d') + ".json"
    )

    if not os.path.exists(transcript_path):
        return jsonify([])

    results = []
    try:
        with open(transcript_path, 'r') as f:
            transcripts = json.load(f)
            
        for t in transcripts:
            path = t.get("Path", "")
            meta = parse_filename_metadata(path)
            
            item = {
                "Time": t.get("Time"), 
                "Text": t.get("Text"),
                "Duration": t.get("Duration"),
                "AudioPath": f"/audio?path={path}", 
                "BusID": "Unknown",
                "Route": "Unknown",
                "Color": "#333",
                "Location": None
            }

            if meta:
                item["BusID"] = meta["bus_id"]
                item["Time"] = meta["time_str"] 
                
                loc_data = find_closest_location(dt, meta["seconds_of_day"], meta["bus_id"])
                if loc_data:
                    item["Route"] = loc_data.get("routeName")
                    item["Color"] = loc_data.get("routeColor")
                    item["Location"] = {
                        "Lat": loc_data.get("lat"),
                        "Long": loc_data.get("lon"),
                        "Heading": loc_data.get("headingDegrees"),
                        "Speed": loc_data.get("speed")
                    }
            
            results.append(item)
            
    except Exception as e:
        log(f"Error processing transcripts: {e}")
        return jsonify([])

    return jsonify(results)

@app.route('/audio')
def stream_audio():
    path = request.args.get('path')
    if not path: abort(404)
    
    clean_path = os.path.abspath(path)
    if not clean_path.startswith(os.path.abspath(BASE_DIR)):
        abort(403)
        
    if not os.path.exists(clean_path):
        abort(404)
        
    return send_file(clean_path)

# --- FRONTEND TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CyRide Dispatch Log</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <style>
        :root {
            --bg-color: #f4f4f9; --paper-color: #ffffff;
            --text-primary: #1a1a1a; --text-secondary: #666;
            --border-color: #e0e0e0;
        }
        body { font-family: 'Segoe UI', Georgia, serif; background: var(--bg-color); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; background: var(--paper-color); padding: 40px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); min-height: 90vh; border-radius: 8px; }
        
        header { border-bottom: 2px solid #eee; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; }
        h1 { margin: 0; font-size: 1.8rem; color: #c8102e; }
        
        .controls { display: flex; gap: 10px; }
        input[type="date"] { padding: 8px; font-size: 1rem; border: 1px solid #ddd; border-radius: 4px; }
        button { padding: 8px 15px; cursor: pointer; background: #333; color: #fff; border: none; border-radius: 4px; }
        button:hover { background: #555; }

        .script-line { 
            margin-bottom: 15px; 
            padding: 10px; 
            display: flex; 
            align-items: baseline; 
            border-bottom: 1px solid #f9f9f9;
            transition: background 0.2s;
        }
        .script-line:hover { background: #fcfcfc; }

        .meta-col { width: 100px; flex-shrink: 0; font-family: monospace; font-size: 0.9rem; color: var(--text-secondary); text-align: right; padding-right: 20px; border-right: 2px solid #eee; margin-right: 20px; }
        .time { font-weight: bold; display: block; }
        
        .dialogue-col { flex-grow: 1; }

        .unit-id { 
            font-weight: 800; 
            text-transform: uppercase; 
            font-size: 0.9rem; 
            cursor: help; 
            display: inline-block; 
            margin-bottom: 4px;
            padding: 2px 6px;
            border-radius: 4px;
            background: #eee;
            position: relative;
        }
        
        .speech { 
            font-size: 1.1rem; 
            line-height: 1.5;
            cursor: pointer; 
            display: block;
            color: #444;
        }
        .speech:hover { color: #000; }
        .speech.playing { background: #e6ffe6; border-radius: 4px; padding: 0 5px; }

        .tooltip { 
            visibility: hidden; 
            width: 250px; 
            background: #fff; 
            border-radius: 8px; 
            position: absolute; 
            z-index: 9999; 
            bottom: 130%; 
            left: 50%; 
            transform: translateX(-50%); 
            opacity: 0; 
            transition: opacity 0.2s, visibility 0.2s; 
            box-shadow: 0 5px 20px rgba(0,0,0,0.2); 
            border: 1px solid #ddd; 
            pointer-events: none; 
        }
        
        .unit-id:hover .tooltip { visibility: visible; opacity: 1; pointer-events: auto; }
        
        .tooltip-header { padding: 8px 12px; background: #f8f9fa; border-bottom: 1px solid #eee; font-weight: bold; font-size: 0.8rem; display: flex; justify-content: space-between; border-radius: 8px 8px 0 0; }
        .tooltip-map { height: 200px; width: 100%; background: #e9ecef; }
        .tooltip-footer { padding: 8px; background: #fff; font-size: 0.75rem; color: #777; border-top: 1px solid #eee; text-align: center; border-radius: 0 0 8px 8px; }
        
        .bus-marker-icon { background: transparent; border: none; }
        
        audio { display: none; }
        .loading { text-align: center; color: #999; margin-top: 50px; }
    </style>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>

<div class="container">
    <header>
        <h1>CyRide Dispatch Log</h1>
        <div class="controls">
            <input type="date" id="date-picker">
            <button onclick="refreshLog()">Load Data</button>
        </div>
    </header>
    <div id="log-container"></div>
</div>

<audio id="audio-player" controls></audio>

<script>
    const tzOffset = new Date().getTimezoneOffset() * 60000; 
    const localISOTime = (new Date(Date.now() - tzOffset)).toISOString().split('T')[0];
    document.getElementById('date-picker').value = localISOTime;
    
    document.getElementById('date-picker').addEventListener('change', (e) => loadTranscript(e.target.value));

    function refreshLog() { 
        loadTranscript(document.getElementById('date-picker').value); 
    }

    function getArrowIcon(color, heading) {
        let rotation = 0, isDir = true;
        if(heading==null || heading==="" || heading=="N/A") isDir=false;
        else rotation=heading;
        
        let svg = isDir ? 
            `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="${color}" stroke="white" stroke-width="1.5" style="transform: rotate(${rotation}deg); transform-origin: center;"><polygon points="12 2 2 22 12 18 22 22 12 2"></polygon></svg>` : 
            `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="${color}" stroke="white" stroke-width="2"/></svg>`;
        return L.divIcon({html: svg, className: 'bus-marker-icon', iconSize: [24,24], iconAnchor:[12,12]});
    }

    window.initMap = function(element, lat, lng, heading, color) {
        if (!element || !lat || !lng) return;
        
        if (element._leaflet_map) {
            setTimeout(() => {
                element._leaflet_map.invalidateSize();
                element._leaflet_map.setView([lat, lng], 16);
            }, 10);
            return;
        }

        const map = L.map(element, {
            zoomControl: false, attributionControl: false, dragging: false,
            scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false,
            keyboard: false
        }).setView([lat, lng], 16);

        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
        L.marker([lat, lng], {icon: getArrowIcon(color, heading)}).addTo(map);
        
        element._leaflet_map = map;
    }

    async function loadTranscript(dateStr) {
        const container = document.getElementById('log-container');
        container.innerHTML = '<div class="loading">Fetching transcripts and cross-referencing locations...</div>';
        
        try {
            const res = await fetch(`/api/data?date=${dateStr}`);
            if(!res.ok) throw new Error("Failed to fetch data");
            const data = await res.json();
            
            container.innerHTML = '';
            
            if(data.length === 0) {
                container.innerHTML = '<div class="loading">No transcripts found for this date.</div>';
                return;
            }
            
            data.forEach((entry, index) => {
                const row = document.createElement('div');
                row.className = 'script-line';
                
                const hasLoc = entry.Location != null;
                const color = entry.Color || "#333";
                
                const lat = hasLoc ? entry.Location.Lat : 0;
                const lng = hasLoc ? entry.Location.Long : 0;
                const heading = hasLoc ? entry.Location.Heading : 0;
                const speed = hasLoc ? Math.round(entry.Location.Speed) + " mph" : "";
                
                const tooltipHTML = hasLoc ? `
                    <div class="tooltip">
                        <div class="tooltip-header">
                            <span>${entry.Route}</span>
                            <span>${speed}</span>
                        </div>
                        <div class="tooltip-map"></div>
                        <div class="tooltip-footer">
                            Lat: ${lat.toFixed(4)}, Lng: ${lng.toFixed(4)}
                        </div>
                    </div>` : `<div class="tooltip" style="width:auto; padding:10px;">No GPS Data</div>`;

                row.innerHTML = `
                    <div class="meta-col">
                        <span class="time">${entry.Time}</span>
                    </div>
                    <div class="dialogue-col">
                        <div class="unit-id" style="color:${color}; background: ${color}20;"
                             onmouseenter="if(${hasLoc}) window.initMap(this.querySelector('.tooltip-map'), ${lat}, ${lng}, ${heading}, '${color}')">
                            BUS ${entry.BusID}
                            ${tooltipHTML}
                        </div>
                        <div class="speech" style="color:${color}" onclick="playAudio('${entry.AudioPath}', this)">
                            ${entry.Text}
                        </div>
                    </div>`;
                
                container.appendChild(row);
            });
            
        } catch(e) {
            container.innerHTML = `<div class="loading" style="color:red">Error: ${e.message}</div>`;
        }
    }

    refreshLog();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    log("--- CyRide Web Interface Starting on Port 80 ---")
    wait_for_drive()
    # Runs on Port 80. Requires sudo or capability (handled by service file).
    app.run(host='0.0.0.0', port=80)
