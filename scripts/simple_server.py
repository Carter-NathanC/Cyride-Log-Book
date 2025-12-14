import os
import sys
import json
import time
import re
import urllib.parse
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import threading
import socketserver

# --- CONFIGURATION ---
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", "/home/sdr/CYRIDE")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
LOCATION_DIR = os.path.join(BASE_DIR, "Location")
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")
PORT = 80

# --- HTML CONTENT ---
# We write this to a file so the server can serve it natively
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CyRide Dispatch Log</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <style>
        :root { --bg-color: #f4f4f9; --paper-color: #ffffff; --text-primary: #1a1a1a; --text-secondary: #666; --border-color: #e0e0e0; }
        body { font-family: 'Georgia', serif; background: var(--bg-color); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; background: var(--paper-color); padding: 40px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); min-height: 90vh; }
        header { border-bottom: 2px solid var(--text-primary); margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; }
        h1 { margin: 0; font-size: 2rem; color: #c8102e; }
        .controls { display: flex; gap: 10px; }
        input[type="date"] { padding: 8px; font-size: 1rem; }
        button { padding: 8px 12px; cursor: pointer; background: #333; color: white; border: none; }
        .script-line { margin-bottom: 24px; display: flex; align-items: baseline; position: relative; }
        .meta-col { width: 140px; flex-shrink: 0; font-family: monospace; font-size: 0.8rem; color: var(--text-secondary); text-align: right; padding-right: 20px; border-right: 1px solid var(--border-color); margin-right: 20px; }
        .time { display: block; font-weight: bold; }
        .channel { display: block; font-size: 0.75rem; opacity: 0.8; }
        .unit-id { font-weight: bold; text-transform: uppercase; font-size: 0.95rem; cursor: help; display: inline-block; border-bottom: 1px dotted #999; position: relative; }
        .speech { font-size: 1.1rem; cursor: pointer; padding: 8px 12px; border-radius: 6px; background: rgba(0,0,0,0.02); display: inline-block; width: 100%; transition: background 0.2s; }
        .speech:hover { background: rgba(0,0,0,0.05); }
        .speech.playing { background: #e6ffe6; border-left: 3px solid #00cc00; }
        .tooltip { visibility: hidden; width: 300px; background: #fff; color: #333; border-radius: 8px; position: absolute; z-index: 9999; bottom: 125%; left: 50%; transform: translateX(-50%); opacity: 0; transition: opacity 0.2s; box-shadow: 0 4px 20px rgba(0,0,0,0.4); border: 1px solid #ccc; pointer-events: none; display: block; }
        .unit-id:hover .tooltip { visibility: visible; opacity: 1; }
        .tooltip-header { padding: 10px; background: #f8f9fa; border-bottom: 1px solid #e9ecef; font-weight: bold; font-size: 0.85rem; display: flex; justify-content: space-between; border-radius: 8px 8px 0 0; }
        .tooltip-map { height: 250px; width: 100%; background: #e9ecef; display: block; }
        .tooltip-footer { padding: 8px; background: #fff; font-size: 0.75rem; color: #666; border-top: 1px solid #e9ecef; text-align: center; border-radius: 0 0 8px 8px; }
        .bus-marker-icon { background: transparent; border: none; }
        .loading { text-align: center; color: #999; padding: 20px; }
        .status-banner { background: #ffeeba; color: #856404; padding: 10px; text-align: center; margin-bottom: 20px; display: none; }
    </style>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
<div class="container">
    <header><h1>CyRide Dispatch Log</h1><div class="controls"><input type="date" id="date-picker"><button onclick="refreshLog()">Refresh</button></div></header>
    <div id="drive-status" class="status-banner">Waiting for Recording Drive...</div>
    <div id="log-container">Loading...</div>
</div>
<audio id="audio-player" controls style="display:none"></audio>
<script>
    const AMES_DEFAULT = { lat: 42.0282, lng: -93.6434 };
    const tzOffset = new Date().getTimezoneOffset() * 60000; 
    const localISOTime = (new Date(Date.now() - tzOffset)).toISOString().slice(0, -1).split('T')[0];
    document.getElementById('date-picker').value = localISOTime;
    document.getElementById('date-picker').addEventListener('change', (e) => loadTranscript(e.target.value));
    
    function refreshLog() { loadTranscript(document.getElementById('date-picker').value); }

    function getArrowIcon(color, heading) {
        let rotation = 0, isDir = true;
        if(heading==null || heading==="" || heading=="N/A" || typeof heading === 'string') isDir=false;
        else rotation=heading;
        let svg = isDir ? 
            `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="${color}" stroke="white" stroke-width="2" style="transform: rotate(${rotation}deg); transform-origin: center;"><polygon points="12 2 2 22 12 18 22 22 12 2"></polygon></svg>` : 
            `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="${color}" stroke="white" stroke-width="2"/></svg>`;
        return L.divIcon({html: svg, className: 'bus-marker-icon', iconSize: [24,24], iconAnchor:[12,12]});
    }

    window.initMap = function(element, lat, lng, heading, color) {
        if (!element || !lat || !lng) return;
        if (element._leaflet_map) {
            element._leaflet_map.invalidateSize();
            element._leaflet_map.setView([lat, lng], 17);
            return;
        }
        const map = L.map(element, { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false }).setView([lat, lng], 17);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
        L.marker([lat, lng], {icon: getArrowIcon(color, heading)}).addTo(map);
        element._leaflet_map = map;
        setTimeout(() => map.invalidateSize(), 200);
    }

    async function loadTranscript(dateStr) {
        const container = document.getElementById('log-container');
        container.innerHTML = '<div class="loading">Loading...</div>';
        try {
            const res = await fetch(`/api/data?date=${dateStr}`);
            const data = await res.json();
            
            if(data.status && data.status.mounted === false) {
                document.getElementById('drive-status').style.display = 'block';
                container.innerHTML = '<div class="loading">Drive Not Mounted</div>';
                return;
            } else {
                document.getElementById('drive-status').style.display = 'none';
            }

            if (!data.entries || data.entries.length === 0) {
                container.innerHTML = `<div class="loading">No transcripts found for ${dateStr}</div>`;
                return;
            }

            container.innerHTML = '';
            data.entries.forEach((entry, index) => {
                const row = document.createElement('div');
                row.className = 'script-line';
                const hasLoc = entry.Location != null;
                const loc = entry.Location || {};
                const color = entry.Color || "#333";
                const headingVal = hasLoc ? (loc.Heading !== undefined ? loc.Heading : null) : null;
                const mapLat = hasLoc ? loc.Lat : AMES_DEFAULT.lat;
                const mapLng = hasLoc ? loc.Long : AMES_DEFAULT.lng;
                const speed = hasLoc ? Math.round(loc.Speed) + " mph" : "";
                
                const tooltipHTML = `<div class="tooltip"><div class="tooltip-header"><span>${entry.Route}</span><span>${speed}</span></div><div class="tooltip-map"></div><div class="tooltip-footer">${hasLoc ? `Lat: ${loc.Lat.toFixed(4)}, Lng: ${loc.Long.toFixed(4)}` : "No GPS Data"}</div></div>`;
                
                row.innerHTML = `<div class="meta-col"><span class="time">${entry.Time}</span><span class="channel">BUS ${entry.BusID}</span></div>
                    <div class="dialogue-col"><div class="unit-id" style="color:${color}" onmouseenter="window.initMap(this.querySelector('.tooltip-map'), ${mapLat}, ${mapLng}, ${headingVal}, '${color}')">[${entry.BusID}]${tooltipHTML}</div>
                    <div class="speech" style="color:${color}" onclick="playAudio('${entry.AudioPath}', this)">${entry.Text}</div></div>`;
                container.appendChild(row);
            });
        } catch(e) { container.innerHTML = `<div class="loading">Error: ${e.message}</div>`; }
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

# --- HELPERS ---

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def parse_filename_metadata(path):
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
    day_loc_dir = os.path.join(LOCATION_DIR, date_obj.strftime('%Y'), date_obj.strftime('%m'), date_obj.strftime('%d'))
    if not os.path.exists(day_loc_dir): return None
    
    # Search ±10 seconds
    for offset in [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8, -8, 9, -9, 10, -10]:
        check_sec = target_seconds + offset
        if check_sec < 0 or check_sec >= 86400: continue
        filename = f"{check_sec//3600:02d}-{(check_sec%3600)//60:02d}-{check_sec%60:02d}.json"
        filepath = os.path.join(day_loc_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    for v in data.get("Vehicles", []):
                        if v.get("name") == bus_id: return v
            except: continue
    return None

# --- REQUEST HANDLER ---

class CyRideHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse URL
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        # 1. SERVE API DATA
        if path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response_data = {"status": {"mounted": os.path.exists(MOUNT_DIR)}, "entries": []}
            
            if response_data["status"]["mounted"] and 'date' in query:
                date_str = query['date'][0]
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    transcript_path = os.path.join(TRANSCRIPT_DIR, dt.strftime('%Y'), dt.strftime('%m'), dt.strftime('%d') + ".json")
                    
                    if os.path.exists(transcript_path):
                        with open(transcript_path, 'r') as f:
                            transcripts = json.load(f)
                        
                        for t in transcripts:
                            meta = parse_filename_metadata(t.get("Path", ""))
                            item = {
                                "Time": t.get("Time"),
                                "Text": t.get("Text"),
                                "AudioPath": f"/audio?path={urllib.parse.quote(t.get('Path', ''))}",
                                "BusID": "Unknown", "Route": "Unknown", "Color": "#333", "Location": None
                            }
                            if meta:
                                item["BusID"] = meta["bus_id"]
                                item["Time"] = meta["time_str"]
                                loc = find_closest_location(dt, meta["seconds_of_day"], meta["bus_id"])
                                if loc:
                                    item["Route"] = loc.get("routeName", "Unknown")
                                    item["Color"] = loc.get("routeColor", "#333")
                                    item["Location"] = {"Lat": loc.get("lat"), "Long": loc.get("lon"), "Heading": loc.get("headingDegrees"), "Speed": loc.get("speed")}
                            response_data["entries"].append(item)
                except Exception as e:
                    log(f"API Error: {e}")

            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        # 2. SERVE AUDIO FILES
        elif path == '/audio':
            if 'path' in query:
                file_path = query['path'][0]
                # Security Check: Must allow Base Directory
                safe_base = os.path.abspath(BASE_DIR)
                clean_path = os.path.abspath(file_path)
                
                if clean_path.startswith(safe_base) and os.path.exists(clean_path):
                    try:
                        file_size = os.path.getsize(clean_path)
                        self.send_response(200)
                        self.send_header('Content-Type', 'audio/mpeg')
                        self.send_header('Content-Length', str(file_size))
                        self.end_headers()
                        with open(clean_path, 'rb') as f:
                            shutil.copyfileobj(f, self.wfile)
                        return
                    except Exception as e:
                        log(f"Audio Error: {e}")
            
            self.send_response(404)
            self.end_headers()
            return

        # 3. SERVE INDEX.HTML (For root or anything else)
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            # Serve from the embedded string directly
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            return

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

def main():
    log("--- CyRide Simple Server Starting ---")
    log(f"Serving on Port {PORT}...")
    
    server_address = ('0.0.0.0', PORT)
    httpd = ThreadingHTTPServer(server_address, CyRideHandler)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    except PermissionError:
        log(f"CRITICAL: Permission denied binding to port {PORT}. Needs CAP_NET_BIND_SERVICE.")
        sys.exit(1)
    
    httpd.server_close()

if __name__ == '__main__':
    main()
