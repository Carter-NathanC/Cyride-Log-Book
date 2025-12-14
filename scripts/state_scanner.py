import os
import json
import hashlib
import time
import argparse
from datetime import datetime, timedelta

# --- CONFIGURATION ---
# Base directories - adjustable via env vars for portability
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", "/home/sdr/CYRIDE")
RECORDINGS_DIR = os.path.join(BASE_DIR, "SDR Recordings")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
STATE_DIR = os.path.join(BASE_DIR, "states")

GROUPS = ["CYRIDE-CIRC", "CYRIDE-FIXED"]

def calculate_md5(filepath, block_size=8192):
    """Calculates MD5 hash of a file efficiently."""
    md5 = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(block_size):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception as e:
        print(f"Error hashing {filepath}: {e}")
        return None

def get_transcript_status(filename, year, month, day):
    """Checks if a file exists in the transcript JSON for that day."""
    transcript_file = os.path.join(TRANSCRIPT_DIR, year, month, f"{day}.json")
    
    if os.path.exists(transcript_file):
        try:
            with open(transcript_file, 'r') as f:
                data = json.load(f)
                # Check if this filename is in the transcripts
                # Transcripts store full path, so check if path ends with filename
                for entry in data:
                    if entry.get('PathToAudio', '').endswith(filename):
                        return "processed"
        except (json.JSONDecodeError, OSError):
            return "error_reading_transcript"
            
    return None

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def load_state_file(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Corrupt state file {filepath}, starting fresh.")
    return {}

def save_state_file(filepath, data):
    try:
        # Atomic write pattern to prevent corruption
        temp_path = filepath + ".tmp"
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, filepath)
    except Exception as e:
        print(f"Error saving state file {filepath}: {e}")

def process_date(target_date):
    """Scans and updates state for a specific date object."""
    year = target_date.strftime('%Y')
    month = target_date.strftime('%m')
    day = target_date.strftime('%d')
    
    # Define state file path: states/YYYY/MM/DD.json
    day_state_dir = os.path.join(STATE_DIR, year, month)
    ensure_dir(day_state_dir)
    state_file_path = os.path.join(day_state_dir, f"{day}.json")
    
    # Load existing state
    current_state = load_state_file(state_file_path)
    state_updated = False
    
    files_found = 0
    
    for group in GROUPS:
        # Path: SDR Recordings/GROUP/YYYY/MM/DD
        group_path = os.path.join(RECORDINGS_DIR, group, year, month, day)
        
        if not os.path.exists(group_path):
            continue
            
        try:
            # List all MP3s
            audio_files = [f for f in os.listdir(group_path) if f.endswith(".mp3")]
            
            for filename in audio_files:
                full_path = os.path.join(group_path, filename)
                files_found += 1
                
                # If file is already in state, we might skip heavy operations like hashing
                # unless we want to force re-verify
                if full_path in current_state:
                    file_data = current_state[full_path]
                    
                    # If status is NOT processed, re-check if it was processed recently
                    if file_data.get('status') != 'processed':
                        real_status = get_transcript_status(filename, year, month, day)
                        if real_status == 'processed':
                            file_data['status'] = 'processed'
                            file_data['TimeUpdated'] = time.time()
                            state_updated = True
                    continue # Skip to next file if already tracked
                
                # --- NEW FILE FOUND ---
                print(f"New file found: {filename}")
                
                # 1. Determine Status
                # Check if it exists in transcripts
                status = get_transcript_status(filename, year, month, day)
                if not status:
                    status = "queue" # Default to queue if not found in transcripts
                
                # 2. Calculate Hash
                file_hash = calculate_md5(full_path)
                
                # 3. Create Entry
                new_entry = {
                    "Path": full_path,
                    "Hash": file_hash,
                    "status": status,
                    "TimeAdded": time.time(),
                    "TimeUpdated": time.time(),
                    "Group": group
                }
                
                current_state[full_path] = new_entry
                state_updated = True
                
        except Exception as e:
            print(f"Error scanning {group_path}: {e}")

    # Check for "Orphaned" entries (files in state that no longer exist on disk)
    # create a list of keys to remove to avoid runtime modification errors
    to_remove = []
    for stored_path in current_state:
        if not os.path.exists(stored_path):
            print(f"File missing from disk, marking error/removed: {stored_path}")
            current_state[stored_path]['status'] = 'error_missing'
            current_state[stored_path]['TimeUpdated'] = time.time()
            state_updated = True

    if state_updated:
        save_state_file(state_file_path, current_state)
        print(f"Updated state for {year}-{month}-{day}: {files_found} files tracked.")
    else:
        print(f"No changes for {year}-{month}-{day}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CyRide Audio State Scanner")
    parser.add_argument("--days", type=int, default=3, help="Number of past days to scan (default: 3)")
    parser.add_argument("--date", type=str, help="Specific date to scan (YYYY-MM-DD)")
    args = parser.parse_args()

    print(f"--- State Scanner Starting ---")
    print(f"Base Dir: {BASE_DIR}")

    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d")
            process_date(target)
        except ValueError:
            print("Invalid date format. Use YYYY-MM-DD")
    else:
        # Scan last N days
        now = datetime.now()
        for i in range(args.days):
            target = now - timedelta(days=i)
            process_date(target)
            
    print("--- Scan Complete ---")
