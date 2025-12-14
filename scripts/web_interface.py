import os
import sys
import json
import time
import re
from datetime import datetime

# Wrap imports in try/except to debug missing modules
try:
    from flask import Flask, render_template_string, request, send_file, jsonify, abort
except ImportError as e:
    print(f"CRITICAL ERROR: Missing Python Module. {e}")
    sys.exit(1)

# --- CONFIGURATION ---
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", "/home/sdr/CYRIDE")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
LOCATION_DIR = os.path.join(BASE_DIR, "Location")
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")

app = Flask(__name__)

def log(msg):
    """Log with timestamp and force flush to systemd journal"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def is_drive_mounted():
    return os.path.exists(MOUNT_DIR)

def parse_filename_metadata(path):
    basename = os.path.basename(path)
    # Regex to handle hh_mm_ss-ID.mp3 or hh-mm-ss-ID.mp3
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
    day_loc_dir = os.path.join(
        LOCATION_DIR, 
        date_obj.strftime('%Y'), 
        date_obj.strftime('%m'), 
        date_obj.strftime('%d')
    )
    
    if not os.path.exists(day_loc_dir):
        return None

    # Search window: Target ± 10 seconds
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
                            return v
            except:
                continue
    return None

# --- ROUTES ---

@app.route('/')
def index():
    if not is_drive_mounted():
        return render_template_string(STATUS_TEMPLATE, 
                                    mounted=False, 
                                    base_dir=BASE_DIR, 
                                    mount_dir=MOUNT_DIR)
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def get_data():
    if not is_drive_mounted():
        return jsonify([])

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
                
                loc = find_closest_location(dt, meta["seconds_of_day"], meta["bus_id"])
                if loc:
                    item["Route"] = loc.get("routeName", "Unknown")
                    item["Color"] = loc.get("routeColor", "#333")
                    item["Location"] = {
                        "Lat": loc.get("lat"),
                        "Long": loc.get("lon"),
                        "Heading": loc.get("headingDegrees"),
                        "Speed": loc.get("speed")
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

# --- TEMPLATES ---

STATUS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>System Status</title>
    <style>
        body { font-family: sans-serif; padding: 50px; text-align: center; background: #f8f9fa; }
        .box { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: inline-block; }
        h1 { color: #dc3545; }
        code { background: #eee; padding: 2px 5px; border-radius: 3px; }
    </style>
    <meta http-equiv="refresh" content="5">
</head>
<body>
    <div class="box">
        <h1>Drive Not Mounted</h1>
        <p>The server is running, but the recording drive is not detected.</p>
        <p>Looking for: <code>{{ mount_dir }}</code></p>
        <p>Base Directory: <code>{{ base_dir }}</code></p>
        <p><em>This page will refresh automatically every 5 seconds...</em></p>
    </div>
</body>
</html>
"""

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
            --border-color: #e0e0e0; --accent: #c8102e;
        }
        body { font-family: 'Georgia', serif; background: var(--bg-color); color: var(--text-primary); margin: 0; padding: 20px; }
        
        .container { max-width: 900px; margin: 0 auto; background: var(--paper-color); padding: 40px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); min-height: 90vh; }
        header { border-bottom: 2px solid var(--text-primary); margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; }
        h1 { margin: 0; font-size: 2rem; }
        
        .controls { display: flex; gap: 10px; }
        input[type="date"] { padding: 8px; font-size: 1rem; }
        button { padding: 8px 12px; cursor: pointer; }

        .script-line { margin-bottom: 24px; display: flex; align-items: baseline; position: relative; }
        .meta-col { width: 140px; flex-shrink: 0; font-family: monospace; font-size: 0.8rem; color: var(--text-secondary); text-align: right; padding-right: 20px; border-right: 1px solid var(--border-color); margin-right: 20px; }
        .time { display: block; font-weight: bold; }
        .channel { display: block; font-size: 0.75rem; opacity: 0.8; }
        
        .unit-id { font-weight: bold; text-transform: uppercase; font-size: 0.95rem; cursor: help; display: inline-block; border-bottom: 1px dotted #999; position: relative; }
        
        .speech { font-size: 1.1rem; cursor: pointer; padding: 8px 12px; border-radius: 6px; background: rgba(0,0,0,0.02); display: inline-block; width: 100%; transition: background 0.2s; }
        .speech:hover { background: rgba(0,0,0,0.05); }
        .speech.playing { background: #e6ffe6; border-left: 3px solid #00cc00; }
        
        .tooltip { 
            visibility: hidden; 
            width: 300px; 
            background: #fff; 
            color: #333; 
            border-radius: 8px; 
            position: absolute; 
            z-index: 9999; 
            bottom: 125%; 
            left: 50%; 
            transform: translateX(-50%); 
            opacity: 0; 
            transition: opacity 0.2s; 
            font-family: sans-serif; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.4); 
            border: 1px solid #ccc; 
            pointer-events: none;
            display: block;
        }
        
        .unit-id:hover .tooltip { visibility: visible; opacity: 1; }
        
        .tooltip-header { padding: 10px; background: #f8f9fa; border-bottom: 1px solid #e9ecef; font-weight: bold; font-size: 0.85rem; display: flex; justify-content: space-between; border-radius: 8px 8px 0 0; }
        .tooltip-map { height: 250px; width: 100%; background: #e9ecef; display: block; }
        .tooltip-footer { padding: 8px; background: #fff; font-size: 0.75rem; color: #666; border-top: 1px solid #e9ecef; text-align: center; border-radius: 0 0 8px 8px; }
        
        .bus-marker-icon { background: transparent; border: none; }
        
        audio { display: none; }
        .loading { text-align: center; color: #999; padding: 20px; }
    </style>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>

<div class="container">
    <header>
        <h1>CyRide Dispatch Log</h1>
        <div class="controls">
            <input type="date" id="date-picker">
            <button onclick="refreshLog()">Refresh</button>
        </div>
    </header>

    <div id="log-container">Loading...</div>
</div>

<audio id="audio-player" controls></audio>

<script>
    const AMES_DEFAULT = { lat: 42.0282, lng: -93.6434 };
    const tzOffset = new Date().getTimezoneOffset() * 60000; 
    const localISOTime = (new Date(Date.now() - tzOffset)).toISOString().slice(0, -1).split('T')[0];
    document.getElementById('date-picker').value = localISOTime;
    
    document.getElementById('date-picker').addEventListener('change', (e) => loadTranscript(e.target.value));
    
    function refreshLog() { loadTranscript(document.getElementById('date-picker').value); }

    function getArrowIcon(color, heading) {
        let rotation = 0, isDir = true;
        if(heading==null || heading==="" || heading=="N/A") isDir=false;
        else if(typeof heading === 'string') isDir=false; 
        else rotation=heading;
        
        let svg = isDir ? 
            `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="${color}" stroke="white" stroke-width="2" style="transform: rotate(${rotation}deg); transform-origin: center;"><polygon points="12 2 2 22 12 18 22 22 12 2"></polygon></svg>` : 
            `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="${color}" stroke="white" stroke-width="2"/></svg>`;
        return L.divIcon({html: svg, className: 'bus-marker-icon', iconSize: [24,24], iconAnchor:[12,12]});
    }

    window.initMap = function(element, lat, lng, heading, color) {
        if (!element || !lat || !lng) return;
        
        if (element._leaflet_map) {
            const map = element._leaflet_map;
            map.invalidateSize();
            map.setView([lat, lng], 17);
            return;
        }

        const map = L.map(element, {
            zoomControl: false, attributionControl: false, dragging: false,
            scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false
        }).setView([lat, lng], 17);

        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19, attribution: ''
        }).addTo(map);

        L.marker([lat, lng], {icon: getArrowIcon(color, heading)}).addTo(map);
        element._leaflet_map = map;
        setTimeout(() => map.invalidateSize(), 200);
    }

    async function loadTranscript(dateStr) {
        const container = document.getElementById('log-container');
        container.innerHTML = '<div class="loading">Loading...</div>';

        try {
            const res = await fetch(`/api/data?date=${dateStr}`);
            if(!res.ok) throw new Error("Server communication error");
            const data = await res.json();
            
            if (data.length === 0) {
                container.innerHTML = `<div class="loading">No transcripts found for ${dateStr}</div>`;
                return;
            }

            container.innerHTML = '';
            
            data.forEach((entry, index) => {
                const row = document.createElement('div');
                row.className = 'script-line';
                
                const hasLoc = entry.Location != null;
                const loc = entry.Location || {};
                const color = entry.Color || "#333";
                
                const headingVal = hasLoc ? (loc.Heading !== undefined ? loc.Heading : null) : null;
                const mapLat = hasLoc ? loc.Lat : AMES_DEFAULT.lat;
                const mapLng = hasLoc ? loc.Long : AMES_DEFAULT.lng;
                const mapColor = hasLoc ? color : '#888';
                const speed = hasLoc ? Math.round(loc.Speed) + " mph" : "";

                const tooltipHTML = `
                    <div class="tooltip">
                        <div class="tooltip-header">
                            <span>${entry.Route}</span>
                            <span>${speed}</span>
                        </div>
                        <div class="tooltip-map"></div>
                        <div class="tooltip-footer">
                            ${hasLoc ? `Lat: ${loc.Lat.toFixed(4)}, Lng: ${loc.Long.toFixed(4)}` : "No GPS Data"}
                        </div>
                    </div>`;
                
                row.innerHTML = `
                    <div class="meta-col">
                        <span class="time">${entry.Time}</span>
                        <span class="channel">BUS ${entry.BusID}</span>
                    </div>
                    <div class="dialogue-col">
                        <div class="unit-id" style="color:${color}" 
                             onmouseenter="window.initMap(this.querySelector('.tooltip-map'), ${mapLat}, ${mapLng}, ${headingVal}, '${mapColor}')">
                            [${entry.BusID}]
                            ${tooltipHTML}
                        </div>
                        <div class="speech" style="color:${color}" onclick="playAudio('${entry.AudioPath}', this)">${entry.Text}</div>
                    </div>`;
                container.appendChild(row);
            });
        } catch(e) { 
            document.getElementById('log-container').innerHTML = `<div style="text-align:center; padding:40px; color:#999">${e.message}</div>`; 
        }
    }

    function playAudio(path, el) {
        document.querySelectorAll('.speech').forEach(x => x.classList.remove('playing'));
        el.classList.add('playing');
        document.getElementById('audio-player').src = path;
        document.getElementById('audio-player').play();
    }

    loadTranscript(localISOTime);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    log("--- CyRide Web Interface Starting ---")
    log("Attempting to bind to Port 80...")
    try:
        app.run(host='0.0.0.0', port=80)
    except PermissionError:
        log("CRITICAL ERROR: Permission Denied for Port 80.")
        sys.exit(1)
    except Exception as e:
        log(f"CRITICAL ERROR: Could not start server. {e}")
        sys.exit(1)
