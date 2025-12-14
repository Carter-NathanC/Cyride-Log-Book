<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CyRide Dispatch Log</title>
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
      crossorigin=""/>
      
    <style>
        :root {
            --bg-color: #f4f4f9; --paper-color: #ffffff;
            --text-primary: #1a1a1a; --text-secondary: #666;
            --border-color: #e0e0e0; --accent: #c8102e;
        }
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
        
        .meta-col { width: 120px; flex-shrink: 0; font-family: monospace; font-size: 0.85rem; color: var(--text-secondary); text-align: right; padding-right: 15px; margin-right: 15px; border-right: 2px solid #eee; display: flex; flex-direction: column; justify-content: center; }
        .time { font-weight: bold; font-size: 1rem; color: #333; }
        .channel { font-size: 0.7rem; text-transform: uppercase; color: #999; margin-top: 4px; }
        
        .dialogue-col { flex-grow: 1; }
        
        .unit-badge { 
            display: inline-block; 
            font-weight: bold; 
            font-size: 0.8rem; 
            padding: 2px 6px; 
            border-radius: 4px; 
            margin-bottom: 4px; 
            cursor: pointer;
            position: relative;
            background: #eee; /* Default */
            color: #333;
        }

        .speech { 
            font-size: 1.1rem; 
            line-height: 1.5;
            cursor: pointer; 
            padding: 8px 12px; 
            border-radius: 6px; 
            background: rgba(0,0,0,0.03); 
            display: block; 
            width: 100%; 
            transition: all 0.2s; 
            border-left: 4px solid transparent;
        }
        .speech:hover { background: rgba(0,0,0,0.06); }
        .speech.playing { background: #eefbee; border-left-color: #28a745; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        
        /* Map Tooltip */
        .tooltip { 
            visibility: hidden; 
            width: 280px; 
            background: #fff; 
            border-radius: 8px; 
            position: absolute; 
            z-index: 9999; 
            bottom: 130%; 
            left: 50%; 
            transform: translateX(-50%); 
            opacity: 0; 
            transition: opacity 0.2s, bottom 0.2s; 
            box-shadow: 0 8px 25px rgba(0,0,0,0.2); 
            border: 1px solid #ddd; 
            pointer-events: none;
        }
        
        .unit-badge:hover .tooltip { visibility: visible; opacity: 1; bottom: 140%; }
        
        .tooltip-header { padding: 8px 12px; background: #f8f9fa; border-bottom: 1px solid #eee; font-weight: bold; font-size: 0.8rem; display: flex; justify-content: space-between; border-radius: 8px 8px 0 0; }
        .tooltip-map { height: 200px; width: 100%; background: #e9ecef; display: block; }
        .tooltip-footer { padding: 8px; background: #fff; font-size: 0.7rem; color: #666; border-top: 1px solid #eee; text-align: center; border-radius: 0 0 8px 8px; }
        
        .bus-marker-icon { background: transparent; border: none; }
        
        /* Sticky Audio Player */
        .audio-dock {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: white;
            border-top: 1px solid #ccc;
            padding: 15px;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
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

<div class="audio-dock">
    <audio id="audio-player" controls></audio>
</div>

<script>
    const AMES_DEFAULT = { lat: 42.0282, lng: -93.6434 };

    // -- Date Setup --
    // Force local date string YYYY-MM-DD
    const today = new Date();
    const localISOTime = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
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

    // Map Initialization (Lazy Loading)
    window.initMap = function(element, lat, lng, heading, color) {
        if (!element || !lat || !lng) return;
        const mapId = element.id;

        // If map already initialized, just ensure size is correct
        if (element._leaflet_map) {
            const map = element._leaflet_map;
            setTimeout(() => {
                map.invalidateSize(); 
                map.setView([lat, lng], 16);
            }, 10);
            return;
        }

        // Delay slightly to ensure element is visible
        setTimeout(() => {
            if (element._leaflet_map) return;

            const map = L.map(mapId, {
                zoomControl: false, attributionControl: false, dragging: false,
                scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false
            }).setView([lat, lng], 16);

            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19, attribution: ''
            }).addTo(map);

            L.marker([lat, lng], {icon: getArrowIcon(color, heading)}).addTo(map);
            
            element._leaflet_map = map;
        }, 50);
    }

    async function loadTranscript(dateStr) {
        const container = document.getElementById('log-container');
        container.innerHTML = '<div class="empty-state">Loading data...</div>';
        
        try {
            // Fetch compiled JSON from the scripts/log_compiler.py output
            // Note: This path works if served from www/ directory
            const res = await fetch(`data/${dateStr}.json?t=${Date.now()}`);
            if(!res.ok) throw new Error("No data found for this date.");
            
            const data = await res.json();
            container.innerHTML = '';
            
            if(data.length === 0) {
                container.innerHTML = '<div class="empty-state">No transcriptions for this day.</div>';
                return;
            }
            
            data.forEach((entry, index) => {
                const row = document.createElement('div');
                row.className = 'script-line';
                
                const loc = entry.Location;
                const hasLoc = loc && loc.Lat && loc.Long;
                
                const uniqueMapId = `map-${index}`;
                const color = entry.Color || '#333';
                const routeName = entry.Route || "Unknown Route";
                
                const headingVal = hasLoc ? (loc.Heading !== undefined ? loc.Heading : null) : null;
                const mapLat = hasLoc ? loc.Lat : AMES_DEFAULT.lat;
                const mapLng = hasLoc ? loc.Long : AMES_DEFAULT.lng;
                
                // --- Tooltip HTML ---
                let tooltipHTML = '';
                if (hasLoc) {
                    tooltipHTML = `
                        <div class="tooltip">
                            <div class="tooltip-header">
                                <span style="color:${color}">${routeName}</span>
                                <span>${loc.Speed ? Math.round(loc.Speed) + ' mph' : '0 mph'}</span>
                            </div>
                            <div id="${uniqueMapId}" class="tooltip-map"></div>
                            <div class="tooltip-footer">
                                ${loc.Lat.toFixed(4)}, ${loc.Long.toFixed(4)}
                            </div>
                        </div>`;
                }

                // --- Unit Badge ---
                // Only enable hover map if we actually have location data
                const hoverAttr = hasLoc ? `onmouseenter="window.initMap(this.querySelector('.tooltip-map'), ${mapLat}, ${mapLng}, ${headingVal}, '${color}')"` : '';
                const unitDisplay = entry.UnitID !== "Unknown" ? `Bus ${entry.UnitID}` : "Unknown Unit";
                
                const unitBadge = `
                    <div class="unit-badge" style="color: ${color}; border: 1px solid ${color}" ${hoverAttr}>
                        ${unitDisplay}
                        ${tooltipHTML}
                    </div>
                `;

                // Clean up path for web serving (remove /home/sdr/CYRIDE/ prefix if serving from root)
                // Assuming we serve "www" as root, and we symlink SDR Recordings into it, 
                // OR we serve the parent folder. 
                // Let's assume the web server root is /home/sdr/CYRIDE, so we need relative links.
                // The compiler outputs full paths like /home/sdr/CYRIDE/SDR Recordings/...
                // The web server running in www/ needs to reach ../SDR Recordings/
                let audioUrl = entry.PathToAudio.replace('/home/sdr/CYRIDE/', '../');

                row.innerHTML = `
                    <div class="meta-col">
                        <span class="time">${entry.Time}</span>
                        <span class="channel">${entry.Channel}</span>
                    </div>
                    <div class="dialogue-col">
                        ${unitBadge}
                        <div class="speech" style="border-left-color: ${color}" onclick="playAudio('${audioUrl}', this)">
                            ${entry.Text}
                        </div>
                    </div>`;
                container.appendChild(row);
            });
        } catch(e) { 
            container.innerHTML = `<div class="empty-state">${e.message}</div>`; 
        }
    }

    function playAudio(path, el) {
        document.querySelectorAll('.speech').forEach(x => x.classList.remove('playing'));
        el.classList.add('playing');
        
        const player = document.getElementById('audio-player');
        player.src = path;
        player.play();
        
        // Auto scroll to next if ended?
        player.onended = () => {
            el.classList.remove('playing');
            // Logic to play next could go here
        };
    }
</script>
</body>
</html>
