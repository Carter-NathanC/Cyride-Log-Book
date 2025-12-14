import os
import sys
import json
import re
import urllib.parse
import http.server
import socketserver
from datetime import datetime

# --- CONFIGURATION ---
# Falls back to local folder if env var not set
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", os.path.abspath("CYRIDE_DATA"))
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
LOCATION_DIR = os.path.join(BASE_DIR, "Location")

# Hardcoded to 8000 to ensure stability on the Runner
PORT = 8000

# --- HTML CONTENT ---
# This is your requested HTML, slightly adapted to fetch from our API
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CyRide Dispatch Log</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
    <style>
        :root { --bg-color: #f4f4f9; --paper-color: #ffffff; --text-primary: #1a1a1a; --text-secondary: #666; --border-color: #e0e0e0; --accent: #c8102e; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg-color); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; background: var(--paper-color); padding: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); min-height: 90vh; border-radius: 8px; }
        header { border-bottom: 2px solid #eee; margin-bottom: 30px; padding-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        h1 { margin: 0; font-size: 1.8rem; color: #333; }
        .controls { display: flex; gap: 10px; align-items: center; }
        input[type="date"] { padding: 10px; font-size: 1rem; border: 1px solid #ddd; border-radius: 4px; }
        button { padding: 10px 20px; cursor: pointer; background: var(--accent); color: white; border: none; border-radius: 4px; font-weight: bold; }
        button:hover { background: #a00c24; }
        .script-line { margin-bottom: 15px; display: flex; align-items: flex-start; padding: 10px; border-radius: 6px; transition: background 0.2s; }
        .script-line:hover { background: #f9f9f9; }
        .meta-col { width: 140px; flex-shrink: 0; font-family: monospace; font-size: 0.85rem; color: var(--text-secondary); text-align: right; padding-right: 15px; margin-right: 15px; border-right: 2px solid #eee; display: flex; flex-direction: column; justify-content: center; }
        .time { font-weight: bold; font-size: 1rem; color: #333; }
        .channel { font-size: 0.7rem; text-transform: uppercase; color: #999; margin-top: 4px; }
        .dialogue-col { flex-grow: 1; }
        .unit-badge { display: inline-block; font-weight: bold; font-size: 0.8rem; padding: 2px 6px; border-radius: 4px; margin-bottom: 4px; cursor: pointer; position: relative; background: #eee; color: #333; border: 1px solid #ccc; }
        .speech { font-size: 1.1rem; line-height: 1.5; cursor: pointer; padding: 8px 12px; border-radius: 6px; background: rgba(0,0,0,0.03); display: block; width: 100%; transition: all 0.2s; border-left: 4px solid transparent; }
        .speech:hover { background: rgba(0,0,0,0.06); }
        .speech.playing { background: #eefbee; border-left-color: #28a745; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .tooltip { visibility: hidden; width: 280px; background: #fff; border-radius: 8px; position: absolute; z-index: 9999; bottom: 130%; left: 50%; transform: translateX(-50%); opacity: 0; transition: opacity 0.2s, bottom 0.2s; box-shadow: 0 8px 25px rgba(0,0,0,0.2); border: 1px solid #ddd; pointer-events: none; }
        .unit-badge:hover .tooltip { visibility: visible; opacity: 1; bottom: 140%; }
        .tooltip-header { padding: 8px 12px; background: #f8f9fa; border-bottom: 1px solid #eee; font-weight: bold; font-size: 0.8rem; display: flex; justify-content: space-between; border-radius: 8px 8px 0 0; }
        .tooltip-map { height: 200px; width: 100%; background: #e9ecef; display: block; }
        .tooltip-footer { padding: 8px; background: #fff; font-size: 0.7rem; color: #666; border-top: 1px solid #eee; text-align: center; border-radius: 0 0 8px 8px; }
        .bus-marker-icon { background: transparent; border: none; }
        .audio-dock { position: fixed; bottom: 0; left: 0; right: 0; background: white; border-top: 1px solid #ccc; padding: 15px; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); display: flex; justify-content: center; align-items: center; z-index: 1000; }
        audio { width: 100%; max-width: 600px; }
        .empty-state { text-align: center; padding: 60px; color: #888; font-style: italic; }
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
    <div id="log-container">
        <div class="empty-state">Select a date to load logs.</div>
    </div>
</div>

<div class="audio-dock"><audio id="audio-player" controls></audio></div>

<script>
    const AMES_DEFAULT = { lat: 42.0282, lng: -93.6434 };
    const tzOffset = new Date().getTimezoneOffset() * 60000; 
    const localISOTime = (new Date(Date.now() - tzOffset)).toISOString().slice(0, -1).split('T')[0];
    document.getElementById('date-picker').value = localISOTime;
    document.getElementById('date-picker').addEventListener('change', (e) => loadTranscript(e.target.value));
    
    // Auto load today
    window.addEventListener('DOMContentLoaded', () => loadTranscript(localISOTime));
    function refreshLog() { loadTranscript(document.getElementById('date-picker').value); }

    function getArrowIcon(color, heading) {
        let rotation = 0, isDir = true;
        if(heading==null || heading==="" || heading=="N/A") isDir=false;
        else rotation=heading;
        let svg = isDir ? 
            `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 24 24" fill="${color}" stroke="white" stroke-width="2" style="transform: rotate(${rotation}deg); transform-origin: center;"><polygon points="12 2 2 22 12 18 22 22 12 2"></polygon></svg>` : 
            `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="${color}" stroke="white" stroke-width="2"/></svg>`;
        return L.divIcon({html: svg, className: 'bus-marker-icon', iconSize: [30,30], iconAnchor:[15,15]});
    }

    window.initMap = function(element, lat, lng, heading, color) {
        if (!element || !lat || !lng) return;
        if (element._leaflet_map) {
            const map = element._leaflet_map;
            setTimeout(() => { map.invalidateSize(); map.setView([lat, lng], 16); }, 10);
            return;
        }
        setTimeout(() => {
            if (element._leaflet_map) return;
            const map = L.map(element, { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false }).setView([lat, lng], 16);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
            L.marker([lat, lng], {icon: getArrowIcon(color, heading)}).addTo(map);
            element._leaflet_map = map;
        }, 50);
    }

    async function loadTranscript(dateStr) {
        const container = document.getElementById('log-container');
        container.innerHTML = '<div class="empty-state">Loading data...</div>';
        
        try {
            // Fetch from our API instead of static file, so we get the location data
            const res = await fetch(`/api/data?date=${dateStr}`);
            if(!res.ok) throw new Error("No data found for this date.");
            
            const data = await res.json();
            container.innerHTML = '';
            
            if(data.entries.length === 0) {
                container.innerHTML = '<div class="empty-state">No transcriptions for this day.</div>';
                return;
            }
            
            data.entries.forEach((entry, index) => {
                const row = document.createElement('div');
                row.className = 'script-line';
                
                const loc = entry.Location || {};
                const hasLoc = loc.Lat && loc.Long;
                const uniqueMapId = `map-${index}`;
                const color = entry.Color || '#333';
                const routeName = entry.Route || "Unknown Route";
                const headingVal = hasLoc ? (loc.Heading !== undefined ? loc.Heading : null) : null;
                const mapLat = hasLoc ? loc.Lat : AMES_DEFAULT.lat;
                const mapLng = hasLoc ? loc.Long : AMES_DEFAULT.lng;
                
                let tooltipHTML = '';
                if (hasLoc) {
                    tooltipHTML = `
                        <div class="tooltip">
                            <div class="tooltip-header">
                                <span style="color:${color}">${routeName}</span>
                                <span>${loc.Speed ? Math.round(loc.Speed) + ' mph' : '0 mph'}</span>
                            </div>
                            <div id="${uniqueMapId}" class="tooltip-map"></div>
                            <div class="tooltip-footer">${loc.Lat.toFixed(4)}, ${loc.Long.toFixed(4)}</div>
                        </div>`;
                }

                const hoverAttr = hasLoc ? `onmouseenter="window.initMap(this.querySelector('.tooltip-map'), ${mapLat}, ${mapLng}, ${headingVal}, '${color}')"` : '';
                const unitDisplay = entry.BusID !== "Unknown" ? `Bus ${entry.BusID}` : "Unknown Unit";
                
                const unitBadge = `
                    <div class="unit-badge" style="color: ${color}; border: 1px solid ${color}" ${hoverAttr}>
                        ${unitDisplay}
                        ${tooltipHTML}
                    </div>
                `;

                row.innerHTML = `
                    <div class="meta-col">
                        <span class="time">${entry.Time}</span>
                        <span class="channel">${entry.Group}</span>
                    </div>
                    <div class="dialogue-col">
                        ${unitBadge}
                        <div class="speech" style="border-left-color: ${color}" onclick="playAudio('${entry.AudioPath}', this)">
                            ${entry.Text}
                        </div>
                    </div>`;
                container.appendChild(row);
            });
        } catch(e) { container.innerHTML = `<div class="empty-state">${e.message}</div>`; }
    }

    function playAudio(path, el) {
        document.querySelectorAll('.speech').forEach(x => x.classList.remove('playing'));
        el.classList.add('playing');
        const player = document.getElementById('audio-player');
        // The path from API is relative to base, so just use it directly
        player.src = path;
        player.play();
        player.onended = () => { el.classList.remove('playing'); };
    }
</script>
</body>
</html>
"""

# --- HELPER FUNCTIONS ---

def parse_metadata(path):
    """
    Extracts time and bus ID from filename: hh_mm_ss-busid.mp3
    And Group from path: .../CYRIDE-CIRC/...
    """
    basename = os.path.basename(path)
    
    # Defaults
    meta = {
        "bus_id": "Unknown",
        "time_display": "00:00:00",
        "seconds": 0,
        "group": "Unknown"
    }

    # 1. Parse Group from path
    if "CYRIDE-CIRC" in path: meta["group"] = "CIRC"
    elif "CYRIDE-FIXED" in path: meta["group"] = "FIXED"

    # 2. Parse Filename (hh_mm_ss-busid.mp3 or hh-mm-ss-busid.mp3)
    match = re.search(r'(\d{2})[_-](\d{2})[_-](\d{2})-(\d+)\.mp3', basename)
    if match:
        h, m, s, bus_id = match.groups()
        
        # Convert to seconds for location lookup
        meta["seconds"] = int(h)*3600 + int(m)*60 + int(s)
        meta["bus_id"] = bus_id
        
        # Convert 24h to 12h AM/PM
        dt = datetime.strptime(f"{h}:{m}:{s}", "%H:%M:%S")
        meta["time_display"] = dt.strftime("%I:%M:%S %p")
    
    return meta

def find_location(date_obj, target_seconds, bus_id):
    """Finds vehicle location in JSON logs for specific time/bus"""
    day_loc_dir = os.path.join(LOCATION_DIR, date_obj.strftime('%Y'), date_obj.strftime('%m'), date_obj.strftime('%d'))
    if not os.path.exists(day_loc_dir): return None
    
    # Look ±10 seconds
    for offset in range(-10, 11):
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
                    for v in data.get("Vehicles", []):
                        # Match Bus ID (Name in JSON)
                        if str(v.get("name")) == str(bus_id): 
                            return v
            except: continue
    return None

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class CyRideHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve files from the BASE_DIR so audio paths work
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        # Parse URL
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        # 1. ROOT -> Serve HTML
        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            return

        # 2. API -> Return Enriched Data
        if path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {"status": {"mounted": os.path.exists(BASE_DIR)}, "entries": []}
            
            if 'date' in query:
                date_str = query['date'][0]
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    transcript_path = os.path.join(TRANSCRIPT_DIR, dt.strftime('%Y'), dt.strftime('%m'), dt.strftime('%d') + ".json")
                    
                    if os.path.exists(transcript_path):
                        with open(transcript_path, 'r') as f:
                            transcripts = json.load(f)
                        
                        for t in transcripts:
                            # 1. Parse info from filename
                            raw_path = t.get("Path", "")
                            meta = parse_metadata(raw_path)
                            
                            # 2. Find Location
                            loc_data = find_location(dt, meta["seconds"], meta["bus_id"])
                            
                            # 3. Build Entry
                            entry = {
                                "Time": meta["time_display"], # Now formatted 12h
                                "Group": meta["group"],       # CIRC or FIXED
                                "BusID": meta["bus_id"],
                                "Text": t.get("Text"),
                                "AudioPath": raw_path.replace(BASE_DIR, ""), # Relative path for browser
                                "Route": "Unknown",
                                "Color": "#333",
                                "Location": None
                            }
                            
                            if loc_data:
                                entry["Route"] = loc_data.get("routeName", "Unknown")
                                entry["Color"] = loc_data.get("routeColor", "#333")
                                entry["Location"] = {
                                    "Lat": loc_data.get("lat"),
                                    "Long": loc_data.get("lon"),
                                    "Heading": loc_data.get("headingDegrees"),
                                    "Speed": loc_data.get("speed")
                                }
                                
                            response["entries"].append(entry)
                except Exception as e:
                    print(f"API Error: {e}")
            
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return

        # 3. EVERYTHING ELSE -> Serve Static Files (Audio, etc)
        # This calls SimpleHTTPRequestHandler logic to serve from BASE_DIR
        return super().do_GET()

if __name__ == '__main__':
    print(f"--- CyRide Web Server Starting on Port {PORT} ---")
    print(f"Serving Directory: {BASE_DIR}")
    
    server_address = ('0.0.0.0', PORT)
    try:
        httpd = ThreadedHTTPServer(server_address, CyRideHandler)
        httpd.serve_forever()
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
