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
STATE_DIR = os.path.join(BASE_DIR, "states")
PORT = 8000

# --- CACHE ---
# Key: "YYYY/MM/DD/HH/MM/SS.json" -> Content
FILE_CACHE = {}

# --- HTML CONTENT ---
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CyRide Dispatch Log</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
    <style>
        :root { --bg-color: #f4f4f9; --paper-color: #ffffff; --text-primary: #1a1a1a; --text-secondary: #666; --border-color: #e0e0e0; --accent: #c8102e; }
        body { font-family: 'Georgia', serif; background: var(--bg-color); color: var(--text-primary); margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; background: var(--paper-color); padding: 40px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); min-height: 90vh; }
        header { border-bottom: 2px solid var(--text-primary); margin-bottom: 30px; }
        .header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        h1 { margin: 0; font-size: 2rem; }
        .tabs { display: flex; gap: 5px; border-bottom: 1px solid #ddd; margin-bottom: 20px; }
        .tab { padding: 10px 20px; cursor: pointer; background: #eee; border-radius: 5px 5px 0 0; border: 1px solid transparent; font-weight: bold; color: #666; }
        .tab.active { background: white; border-color: #ddd; border-bottom-color: white; color: var(--accent); }
        .view-section { display: none; }
        .view-section.active { display: block; }
        .controls { display: flex; gap: 10px; }
        input[type="date"] { padding: 8px; font-size: 1rem; }
        button { padding: 8px 12px; cursor: pointer; }
        #sort-btn { min-width: 120px; }
        .script-line { margin-bottom: 24px; display: flex; align-items: baseline; position: relative; animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
        .meta-col { width: 140px; flex-shrink: 0; font-family: monospace; font-size: 0.8rem; color: var(--text-secondary); text-align: right; padding-right: 20px; border-right: 1px solid var(--border-color); margin-right: 20px; }
        .time { display: block; font-weight: bold; }
        .channel { display: block; font-size: 0.75rem; opacity: 0.8; }
        .unit-id { font-weight: bold; text-transform: uppercase; font-size: 0.95rem; cursor: help; display: inline-block; border-bottom: 1px dotted #999; position: relative; }
        .speech { font-size: 1.1rem; cursor: pointer; padding: 8px 12px; border-radius: 6px; background: rgba(0,0,0,0.02); display: inline-block; width: 100%; transition: background 0.2s; }
        .speech:hover { background: rgba(0,0,0,0.05); }
        .speech.playing { background: #e6ffe6; border-left: 3px solid #00cc00; }
        .tooltip { visibility: hidden; width: 300px; background: #fff; color: #333; border-radius: 8px; position: absolute; z-index: 9999; bottom: 125%; left: 50%; transform: translateX(-50%); opacity: 0; transition: opacity 0.2s; font-family: sans-serif; box-shadow: 0 4px 20px rgba(0,0,0,0.4); border: 1px solid #ccc; pointer-events: none; display: block; }
        .unit-id:hover .tooltip { visibility: visible; opacity: 1; }
        .tooltip-header { padding: 10px; background: #f8f9fa; border-bottom: 1px solid #e9ecef; font-weight: bold; font-size: 0.85rem; display: flex; justify-content: space-between; border-radius: 8px 8px 0 0; }
        .tooltip-map { height: 250px; width: 100%; background: #e9ecef; display: block; }
        .tooltip-footer { padding: 8px; background: #fff; font-size: 0.75rem; color: #666; border-top: 1px solid #e9ecef; text-align: center; border-radius: 0 0 8px 8px; }
        .bus-marker-icon { background: transparent; border: none; }
        .status-container { max-height: 70vh; overflow-y: auto; border: 1px solid #eee; border-radius: 4px; padding: 10px; font-family: monospace; }
        .status-row { padding: 5px 10px; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; }
        .status-row:last-child { border-bottom: none; }
        .status-file { flex-grow: 1; }
        .status-badge { font-weight: bold; text-transform: uppercase; font-size: 0.8rem; padding: 2px 6px; border-radius: 4px; color: #fff; min-width: 80px; text-align: center;}
        .st-processed { background-color: #28a745; } 
        .st-queue { background-color: #ffc107; color: #333; }
        .st-processing { background-color: #fd7e14; }
        .st-error { background-color: #dc3545; }
        .st-unknown { background-color: #6c757d; }
        .audio-dock { position: fixed; bottom: 0; left: 0; right: 0; background: white; border-top: 1px solid #ccc; padding: 10px; display: flex; justify-content: center; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); z-index: 10000; }
        #audio-player { width: 100%; max-width: 600px; display: block; }
        .loader { text-align: center; padding: 20px; color: #999; font-style: italic; }
    </style>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
<div class="container">
    <header>
        <div class="header-row">
            <h1>CyRide Dispatch Log</h1>
            <div class="controls"><input type="date" id="date-picker"><button onclick="refreshCurrentView()">Refresh</button></div>
        </div>
        <div class="tabs"><div class="tab active" onclick="switchTab('logs')">Transcripts</div><div class="tab" onclick="switchTab('worker')">Worker Status</div></div>
    </header>
    <div id="view-logs" class="view-section active">
        <div style="margin-bottom:15px; text-align:right;"><button id="sort-btn" onclick="toggleSort()">Sort: ⬆ Time</button></div>
        <div id="log-container"></div>
        <div id="loading-indicator" class="loader" style="display:none;">Loading more...</div>
    </div>
    <div id="view-worker" class="view-section">
        <div id="worker-container" class="status-container"><div class="loader">Loading status...</div></div>
    </div>
</div>
<div class="audio-dock"><audio id="audio-player" controls></audio></div>
<script>
    const FALLBACK_LOC = { lat: 42.027726571599906, lng: -93.63560572572788 };
    const tzOffset = new Date().getTimezoneOffset() * 60000; 
    const localISOTime = (new Date(Date.now() - tzOffset)).toISOString().slice(0, -1).split('T')[0];
    let currentView = 'logs'; let currentOffset = 0; let activeDateStr = localISOTime; let stopLoading = false; let sortOrder = 'asc'; 
    const dateInput = document.getElementById('date-picker');
    dateInput.value = localISOTime;
    dateInput.addEventListener('change', (e) => { activeDateStr = e.target.value; refreshCurrentView(); });
    function switchTab(tabName) {
        currentView = tabName;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.view-section').forEach(v => v.classList.remove('active'));
        document.querySelector(`.tab[onclick="switchTab('${tabName}')"]`).classList.add('active');
        document.getElementById(`view-${tabName}`).classList.add('active');
        refreshCurrentView();
    }
    function refreshCurrentView() { if(currentView === 'logs') { loadTranscript(activeDateStr); } else { loadWorkerStatus(activeDateStr); } }
    function toggleSort() {
        sortOrder = (sortOrder === 'asc') ? 'desc' : 'asc';
        document.getElementById('sort-btn').innerText = (sortOrder === 'asc') ? "Sort: ⬆ Time" : "Sort: ⬇ Time";
        loadTranscript(activeDateStr);
    }
    async function loadWorkerStatus(dateStr) {
        const container = document.getElementById('worker-container');
        container.innerHTML = '<div class="loader">Loading status...</div>';
        try {
            const res = await fetch(`/api/status?date=${dateStr}`);
            if (!res.ok) throw new Error("Status not found");
            const data = await res.json();
            if (Object.keys(data).length === 0) { container.innerHTML = '<div class="loader">No worker history for this date.</div>'; return; }
            container.innerHTML = '';
            const files = Object.keys(data).sort().reverse();
            files.forEach(f => {
                const info = data[f];
                let badgeClass = 'st-unknown';
                if (info.status === 'processed') badgeClass = 'st-processed';
                else if (info.status === 'queue') badgeClass = 'st-queue';
                else if (info.status === 'processing') badgeClass = 'st-processing';
                else if (info.status === 'error') badgeClass = 'st-error';
                const div = document.createElement('div');
                div.className = 'status-row';
                div.innerHTML = `<div class="status-file">${f.split('/').pop()}</div><div class="status-badge ${badgeClass}">${info.status}</div>`;
                container.appendChild(div);
            });
        } catch (e) { container.innerHTML = `<div class="loader">Error: ${e.message}</div>`; }
    }
    function getArrowIcon(color, headingDegrees, isOOS) {
        if (isOOS || headingDegrees == null || headingDegrees === "" || isNaN(headingDegrees)) {
             return L.divIcon({ html: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="${color}" stroke="white" stroke-width="2"/></svg>`, className: 'bus-marker-icon', iconSize: [24,24], iconAnchor:[12,12] });
        }
        return L.divIcon({ html: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="${color}" stroke="white" stroke-width="2" style="transform: rotate(${headingDegrees}deg); transform-origin: center;"><polygon points="12 2 2 22 12 18 22 22 12 2"></polygon></svg>`, className: 'bus-marker-icon', iconSize: [24,24], iconAnchor:[12,12] });
    }
    window.initMap = function(element, lat, lng, heading, color, isOOS) {
        if (!element || !lat || !lng) return;
        if (element._leaflet_map) { element._leaflet_map.invalidateSize(); element._leaflet_map.setView([lat, lng], 17); return; }
        setTimeout(() => {
            if (element._leaflet_map) return;
            const map = L.map(element.id, { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false }).setView([lat, lng], 17);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
            L.marker([lat, lng], {icon: getArrowIcon(color, heading, isOOS)}).addTo(map);
            element._leaflet_map = map;
            map.invalidateSize();
        }, 50);
    }
    async function loadTranscript(dateStr) {
        activeDateStr = dateStr; currentOffset = 0; stopLoading = true;
        document.getElementById('log-container').innerHTML = ''; document.getElementById('loading-indicator').style.display = 'block';
        await new Promise(r => setTimeout(r, 50)); stopLoading = false; fetchNextBatch();
    }
    async function fetchNextBatch() {
        if (stopLoading) return;
        try {
            const res = await fetch(`/api/data?date=${activeDateStr}&offset=${currentOffset}&limit=10&sort=${sortOrder}`);
            if(!res.ok) throw new Error("API Error");
            const data = await res.json();
            if (stopLoading) return;
            if (data.entries.length === 0 && currentOffset === 0) { document.getElementById('log-container').innerHTML = `<div class="loader">No recordings.</div>`; document.getElementById('loading-indicator').style.display = 'none'; return; }
            renderEntries(data.entries);
            if (data.has_more) { currentOffset += 10; fetchNextBatch(); } else { document.getElementById('loading-indicator').style.display = 'none'; }
        } catch(e) { document.getElementById('loading-indicator').innerText = "Error loading data."; }
    }
    function renderEntries(entries) {
        const container = document.getElementById('log-container');
        entries.forEach((entry, index) => {
            const row = document.createElement('div'); row.className = 'script-line';
            const loc = entry.Location || {}; const hasLoc = loc.Lat && loc.Long;
            const uniqueMapId = `map-${currentOffset + index}`;
            const color = entry.Color || '#333';
            const isOOS = (entry.Route === "Out Of Service" || entry.Route === "DISPATCH");
            const headingVal = hasLoc ? (loc.Heading !== undefined ? loc.Heading : null) : null;
            const mapLat = hasLoc ? loc.Lat : FALLBACK_LOC.lat;
            const mapLng = hasLoc ? loc.Long : FALLBACK_LOC.lng;
            const mapColor = hasLoc ? color : '#888';
            const tooltipHTML = `<div class="tooltip"><div class="tooltip-header"><span>${entry.Route}</span><span>${loc.Speed ? Math.round(loc.Speed) + ' mph' : '0 mph'}</span></div><div id="${uniqueMapId}" class="tooltip-map"></div><div class="tooltip-footer">${hasLoc ? `Lat: ${loc.Lat.toFixed(4)}, Lng: ${loc.Long.toFixed(4)}` : "Position Unavailable"}</div></div>`;
            const audioPath = `/audio?path=${encodeURIComponent(entry.AudioPath)}`;
            row.innerHTML = `<div class="meta-col"><span class="time">${entry.FormattedTime}</span><span class="channel">${entry.Channel}</span></div><div class="dialogue-col"><div class="unit-id" style="color:${color}" onmouseenter="window.initMap(this.querySelector('.tooltip-map'), ${mapLat}, ${mapLng}, ${headingVal}, '${mapColor}', ${isOOS})">[${entry.BusID}]${tooltipHTML}</div><div class="speech" style="color:${color}" onclick="playAudio('${audioPath}', this)">${entry.Text}</div></div>`;
            container.appendChild(row);
        });
    }
    function playAudio(path, el) { document.querySelectorAll('.speech').forEach(x => x.classList.remove('playing')); el.classList.add('playing'); const player = document.getElementById('audio-player'); player.src = path; player.play(); }
    loadTranscript(localISOTime);
</script>
</body>
</html>
"""

# --- HELPERS ---

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def parse_filename_metadata(path):
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
    # Optimized search: Looks for HH/MM/SS.json 
    # Searches 0 to -10 seconds (closest past time)
    search_offsets = [0, -1, -2, -3, -4, -5, -6, -7, -8, -9, -10]

    for offset in search_offsets:
        check_sec = target_seconds + offset
        if check_sec < 0 or check_sec >= 86400: continue
        
        h = check_sec // 3600
        m = (check_sec % 3600) // 60
        s = check_sec % 60
        
        # New optimized path: Location/YYYY/MM/DD/HH/MM/SS.json
        full_path = os.path.join(
            LOCATION_DIR, 
            date_obj.strftime('%Y'), 
            date_obj.strftime('%m'), 
            date_obj.strftime('%d'),
            f"{h:02d}",
            f"{m:02d}",
            f"{s:02d}.json"
        )
        
        # Cache Check
        if full_path in FILE_CACHE:
            data = FILE_CACHE[full_path]
        elif os.path.exists(full_path):
            try:
                with open(full_path, 'r') as f:
                    data = json.load(f)
                    FILE_CACHE[full_path] = data
            except: continue
        else:
            continue

        # File found (either in cache or just loaded), now search vehicles
        vehicles = data.get("Vehicles", [])
        for v in vehicles:
            if str(v.get("name")) == str(bus_id):
                return v # Found the bus in the closest past file
    
    return None

def process_route_name(route_name, bus_id):
    if not route_name or route_name == "Out Of Service":
        if str(bus_id) in ["CY-BASE", "MOBILE"]: return "DISPATCH", "#333"
        return "Out Of Service", "#808080"
    return route_name, None 

# --- REQUEST HANDLER ---

class CyRideHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        if path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            response_data = {"status": {"mounted": os.path.exists(MOUNT_DIR)}, "entries": [], "has_more": False}
            
            if 'date' in query:
                date_str = query.get('date', [None])[0]
                try: offset = int(query.get('offset', [0])[0])
                except: offset = 0
                try: limit = int(query.get('limit', [10])[0])
                except: limit = 10
                try: sort_order = query.get('sort', ['asc'])[0]
                except: sort_order = 'asc'
                
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    transcript_path = os.path.join(TRANSCRIPT_DIR, dt.strftime('%Y'), dt.strftime('%m'), dt.strftime('%d') + ".json")
                    if os.path.exists(transcript_path):
                        with open(transcript_path, 'r') as f: transcripts = json.load(f)
                        
                        def get_timestamp(entry):
                            meta = parse_filename_metadata(entry.get("Path", ""))
                            return meta["seconds_of_day"] if meta else -1
                        
                        transcripts.sort(key=get_timestamp)
                        if sort_order == 'desc': transcripts.reverse()
                        
                        total_items = len(transcripts)
                        chunk = transcripts[offset : offset + limit]
                        response_data["has_more"] = (offset + limit) < total_items
                        
                        for t in chunk:
                            file_path = t.get("Path", "")
                            meta = parse_filename_metadata(file_path)
                            if not meta: continue 
                            
                            item = {
                                "Text": t.get("Text", ""),
                                "AudioPath": file_path,
                                "BusID": meta["bus_id"],
                                "FormattedTime": format_time_12hr(meta["h"], meta["m"], meta["s"]),
                                "Channel": determine_channel(file_path),
                                "Route": "Unknown", "Color": "#333", "Location": {}
                            }
                            
                            loc = find_closest_location(dt, meta["seconds_of_day"], meta["bus_id"])
                            if loc:
                                r_name, r_color = process_route_name(loc.get("routeName"), meta["bus_id"])
                                item["Route"] = r_name
                                item["Color"] = r_color if r_color else loc.get("routeColor", "#333")
                                item["Location"] = { "Lat": loc.get("lat"), "Long": loc.get("lon"), "Heading": loc.get("headingDegrees"), "Speed": loc.get("speed") }
                            else:
                                r_name, r_color = process_route_name(None, meta["bus_id"])
                                item["Route"] = r_name
                                item["Color"] = r_color if r_color else "#888"
                            response_data["entries"].append(item)
                except Exception as e: log(f"API Error: {e}")
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            return

        elif path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            status_data = {}
            if 'date' in query:
                date_str = query.get('date', [None])[0]
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    state_file_path = os.path.join(STATE_DIR, dt.strftime('%Y'), dt.strftime('%m'), f"{dt.strftime('%d')}.json")
                    if os.path.exists(state_file_path):
                        with open(state_file_path, 'r') as f: status_data = json.load(f)
                except Exception: pass
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
            return

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
                        with open(file_path, 'rb') as f: shutil.copyfileobj(f, self.wfile)
                        return
                    except Exception as e: log(f"Audio Serve Error: {e}")
            self.send_response(404)
            self.end_headers()
            return

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
