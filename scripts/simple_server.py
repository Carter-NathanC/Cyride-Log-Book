import os
import sys
import json
import urllib.parse
import shutil
import re
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# --- CONFIGURATION ---
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", os.path.abspath("CYRIDE_DATA"))
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
LOCATION_DIR = os.path.join(BASE_DIR, "Location")
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")
PORT = 8000

# --- HTML CONTENT ---
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CyRide Dispatch Log</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
      crossorigin=""/>
      
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
        
        /* Map Tooltip */
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
        
        /* Sticky Audio Player */
        .audio-dock { position: fixed; bottom: 0; left: 0; right: 0; background: white; border-top: 1px solid #ccc; padding: 10px; display: flex; justify-content: center; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); z-index: 10000; }
        #audio-player { width: 100%; max-width: 600px; display: block; }
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

<div class="audio-dock">
    <audio id="audio-player" controls></audio>
</div>

<script>
    // Fallback Location provided by user
    const FALLBACK_LOC = { lat: 42.027726571599906, lng: -93.63560572572788 };

    // -- Date Setup --
    const tzOffset = new Date().getTimezoneOffset() * 60000; 
    const localISOTime = (new Date(Date.now() - tzOffset)).toISOString().slice(0, -1).split('T')[0];
    document.getElementById('date-picker').value = localISOTime;
    
    document.getElementById('date-picker').addEventListener('change', (e) => loadTranscript(e.target.value));
    function refreshLog() { loadTranscript(document.getElementById('date-picker').value); }

    // Generates the icon: Arrow if moving/headed, Dot if OOS/Stopped
    function getArrowIcon(color, headingDegrees, isOOS) {
        let useDot = false;
        
        // If Out of Service, or heading is invalid/missing, use dot
        if (isOOS || headingDegrees == null || headingDegrees === "" || isNaN(headingDegrees)) {
            useDot = true;
        }

        if (useDot) {
             return L.divIcon({
                html: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="${color}" stroke="white" stroke-width="2"/></svg>`,
                className: 'bus-marker-icon', 
                iconSize: [24,24], 
                iconAnchor:[12,12]
            });
        }
        
        // Arrow rotated by heading degrees
        return L.divIcon({
            html: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="${color}" stroke="white" stroke-width="2" style="transform: rotate(${headingDegrees}deg); transform-origin: center;"><polygon points="12 2 2 22 12 18 22 22 12 2"></polygon></svg>`,
            className: 'bus-marker-icon', 
            iconSize: [24,24], 
            iconAnchor:[12,12]
        });
    }

    // Map Initialization
    window.initMap = function(element, lat, lng, heading, color, isOOS) {
        if (!element || !lat || !lng) return;
        const mapId = element.id;

        if (element._leaflet_map) {
            const map = element._leaflet_map;
            map.invalidateSize();
            map.setView([lat, lng], 17);
            setTimeout(() => map.invalidateSize(), 200);
            return;
        }

        setTimeout(() => {
            if (element._leaflet_map) return;

            const map = L.map(element, {
                zoomControl: false, attributionControl: false, dragging: false,
                scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false
            }).setView([lat, lng], 17);

            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19, attribution: ''
            }).addTo(map);

            L.marker([lat, lng], {icon: getArrowIcon(color, heading, isOOS)}).addTo(map);
            
            element._leaflet_map = map;
            map.invalidateSize();
            setTimeout(() => map.invalidateSize(), 250); 
        }, 50);
    }

    async function loadTranscript(dateStr) {
        const container = document.getElementById('log-container');
        container.innerHTML = '<div style="text-align:center;color:#999">Loading data...</div>';
        
        try {
            const res = await fetch(`/api/data?date=${dateStr}`);
            if(!res.ok) throw new Error("No log found");
            
            const data = await res.json();
            
            if (data.entries.length === 0) {
                container.innerHTML = `<div style="text-align:center;color:#999">No recordings found for ${dateStr}</div>`;
                return;
            }

            container.innerHTML = '';
            
            data.entries.forEach((entry, index) => {
                const row = document.createElement('div');
                row.className = 'script-line';
                const loc = entry.Location || {};
                const hasLoc = loc.Lat && loc.Long;
                
                const uniqueMapId = `map-${index}`;
                const color = entry.Color || '#333';
                const isOOS = (entry.Route === "Out Of Service" || entry.Route === "DISPATCH");
                
                const headingVal = hasLoc ? (loc.Heading !== undefined ? loc.Heading : null) : null;
                const mapLat = hasLoc ? loc.Lat : FALLBACK_LOC.lat;
                const mapLng = hasLoc ? loc.Long : FALLBACK_LOC.lng;
                const mapColor = hasLoc ? color : '#888';

                const tooltipHTML = `
                    <div class="tooltip">
                        <div class="tooltip-header">
                            <span>${entry.Route}</span>
                            <span>${loc.Speed ? Math.round(loc.Speed) + ' mph' : '0 mph'}</span>
                        </div>
                        <div id="${uniqueMapId}" class="tooltip-map"></div>
                        <div class="tooltip-footer">
                            ${hasLoc ? `Lat: ${loc.Lat.toFixed(4)}, Lng: ${loc.Long.toFixed(4)}` : "Position Unavailable"}
                        </div>
                    </div>`;
                
                const audioPath = `/audio?path=${encodeURIComponent(entry.AudioPath)}`;
                
                row.innerHTML = `
                    <div class="meta-col">
                        <span class="time">${entry.FormattedTime}</span>
                        <span class="channel">${entry.Channel}</span>
                    </div>
                    <div class="dialogue-col">
                        <div class="unit-id" style="color:${color}" 
                             onmouseenter="window.initMap(this.querySelector('.tooltip-map'), ${mapLat}, ${mapLng}, ${headingVal}, '${mapColor}', ${isOOS})">
                            [${entry.BusID}]
                            ${tooltipHTML}
                        </div>
                        <div class="speech" style="color:${color}" onclick="playAudio('${audioPath}', this)">${entry.Text}</div>
                    </div>`;
                container.appendChild(row);
            });
        } catch(e) { 
            container.innerHTML = `<div style="text-align:center; padding:40px; color:#999">${e.message}</div>`; 
        }
    }

    function playAudio(path, el) {
        document.querySelectorAll('.speech').forEach(x => x.classList.remove('playing'));
        el.classList.add('playing');
        const player = document.getElementById('audio-player');
        player.src = path;
        player.play();
    }

    loadTranscript(localISOTime);
</script>
</body>
</html>
"""

# --- HELPERS ---

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def parse_filename_metadata(path):
    """
    Extracts time and bus ID from filename like: 14_30_05-1234.mp3
    Returns: { "h": 14, "m": 30, "s": 5, "bus_id": "1234" }
    """
    basename = os.path.basename(path)
    match = re.search(r'(\d{2})[_-](\d{2})[_-](\d{2})-(.+)\.mp3', basename)
    if match:
        h, m, s, bus_id = match.groups()
        return {
            "h": int(h), "m": int(m), "s": int(s),
            "seconds_of_day": int(h)*3600 + int(m)*60 + int(s),
            "bus_id": bus_id
        }
    return None

def format_time_12hr(h, m, s):
    """Converts 24h to 12h AM/PM string"""
    period = "AM"
    if h >= 12:
        period = "PM"
        if h > 12: h -= 12
    if h == 0: h = 12
    return f"{h}:{m:02d}:{s:02d} {period}"

def determine_channel(path):
    if "CYRIDE-CIRC" in path: return "CIRC"
    if "CYRIDE-FIXED" in path: return "FIXED"
    return "UNK"

def find_closest_location(date_obj, target_seconds, bus_id):
    day_loc_dir = os.path.join(
        LOCATION_DIR, 
        date_obj.strftime('%Y'), 
        date_obj.strftime('%m'), 
        date_obj.strftime('%d')
    )
    
    if not os.path.exists(day_loc_dir):
        return None

    search_offsets = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5]

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
                        # Convert both to string to ensure matching numbers vs strings
                        if str(v.get("name")) == str(bus_id):
                            return v
            except:
                continue
    return None

def process_route_name(route_name, bus_id):
    if not route_name or route_name == "Out Of Service":
        if str(bus_id) in ["CY-BASE", "MOBILE"]:
            return "DISPATCH", "#333"
        return "Out Of Service", "#808080"
    return route_name, None 

# --- REQUEST HANDLER ---

class CyRideHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        # 1. API: GET DATA
        if path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response_data = {"status": {"mounted": os.path.exists(MOUNT_DIR)}, "entries": []}
            
            if 'date' in query:
                date_str = query['date'][0]
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    transcript_path = os.path.join(
                        TRANSCRIPT_DIR, 
                        dt.strftime('%Y'), 
                        dt.strftime('%m'), 
                        dt.strftime('%d') + ".json"
                    )
                    
                    if os.path.exists(transcript_path):
                        with open(transcript_path, 'r') as f:
                            transcripts = json.load(f)
                        
                        for t in transcripts:
                            file_path = t.get("Path", "")
                            meta = parse_filename_metadata(file_path)
                            
                            if not meta: continue 
                            
                            item = {
                                "Text": t.get("Text", ""),
                                "AudioPath": file_path,
                                "BusID": meta["bus_id"],
                                "FormattedTime": format_time_12hr(meta["h"], meta["m"], meta["s"]),
                                "Channel": determine_channel(file_path),
                                "Route": "Unknown",
                                "Color": "#333",
                                "Location": {}
                            }
                            
                            loc = find_closest_location(dt, meta["seconds_of_day"], meta["bus_id"])
                            
                            if loc:
                                r_name, r_color = process_route_name(loc.get("routeName"), meta["bus_id"])
                                item["Route"] = r_name
                                item["Color"] = r_color if r_color else loc.get("routeColor", "#333")
                                item["Location"] = {
                                    "Lat": loc.get("lat"),
                                    "Long": loc.get("lon"),
                                    "Heading": loc.get("headingDegrees"), # Sending degrees for rotation
                                    "Speed": loc.get("speed")
                                }
                            else:
                                r_name, r_color = process_route_name(None, meta["bus_id"])
                                item["Route"] = r_name
                                item["Color"] = r_color if r_color else "#888"

                            response_data["entries"].append(item)
                            
                except Exception as e:
                    log(f"API Error: {e}")

            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        # 2. API: AUDIO STREAMING
        elif path == '/audio':
            if 'path' in query:
                file_path = query['path'][0]
                if os.path.exists(file_path):
                    try:
                        file_size = os.path.getsize(file_path)
                        self.send_response(200)
                        self.send_header('Content-Type', 'audio/mpeg')
                        self.send_header('Content-Length', str(file_size))
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        with open(file_path, 'rb') as f:
                            shutil.copyfileobj(f, self.wfile)
                        return
                    except Exception as e:
                        log(f"Audio Serve Error: {e}")
            
            self.send_response(404)
            self.end_headers()
            return

        # 3. UI: SERVE HTML
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            return

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

def main():
    log("--- CyRide Simple Server Starting ---")
    log(f"Serving on Port {PORT}...")
    
    try:
        server_address = ('0.0.0.0', PORT)
        httpd = ThreadingHTTPServer(server_address, CyRideHandler)
        httpd.serve_forever()
    except Exception as e:
        log(f"CRITICAL ERROR: Could not bind to Port {PORT}: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
