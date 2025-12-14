import os
import json
import time
import sys
import torch
import whisper
import tempfile
from datetime import datetime, timedelta
from pydub import AudioSegment

BASE_DIR = os.getenv("CYRIDE_BASE_DIR", os.path.abspath("CYRIDE_DATA"))
STATE_DIR = os.path.join(BASE_DIR, "states")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")
MOUNT_DIR = os.path.join(BASE_DIR, "SDR Recordings")
WHISPER_MODEL_SIZE = "medium.en" 

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def wait_for_mount():
    log(f"Checking for mount at: {BASE_DIR}")
    while True:
        if os.path.ismount(BASE_DIR) or os.path.exists(MOUNT_DIR):
            log("Mount detected. Proceeding.")
            break
        log("Waiting for Google Drive to mount...")
        time.sleep(10)

def clean_audio(input_path):
    try:
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio = audio.high_pass_filter(300).low_pass_filter(3400).normalize()
        temp_path = input_path + ".temp.wav"
        audio.export(temp_path, format="wav")
        return temp_path, audio.duration_seconds
    except Exception as e:
        log(f"Audio cleaning failed for {input_path}: {e}")
        return None, 0

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f: return json.load(f)
        except: return None # Return None on failure to avoid overwrites
    return {}

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # ATOMIC WRITE: Write to temp, rename. Prevents race conditions.
    dir_name = os.path.dirname(filepath)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False) as tf:
        json.dump(data, tf, indent=4)
        tempname = tf.name
    try:
        os.replace(tempname, filepath)
    except Exception:
        if os.path.exists(tempname): os.remove(tempname)

def append_transcription(date_obj, entry):
    path = os.path.join(TRANSCRIPT_DIR, date_obj.strftime('%Y'), date_obj.strftime('%m'), f"{date_obj.strftime('%d')}.json")
    current_data = load_json(path)
    if not isinstance(current_data, list): current_data = []
    current_data.append(entry)
    save_json(path, current_data)
    log(f"Saved transcription to {path}")

def update_status(state_file_path, file_key, new_status):
    # Retry loop for status updates to handle contention
    for _ in range(3):
        data = load_json(state_file_path)
        if data is None: 
            time.sleep(0.5)
            continue
        
        if file_key in data:
            data[file_key]["status"] = new_status
            save_json(state_file_path, data)
            return
    log(f"Failed to update status for {file_key}")

def process_file(model, file_path, file_data, state_file_path, date_obj):
    log(f"Processing: {file_path}")
    update_status(state_file_path, file_path, "processing")
    clean_path, duration = clean_audio(file_path)
    if not clean_path:
        update_status(state_file_path, file_path, "error")
        return
    try:
        result = model.transcribe(clean_path, fp16=torch.cuda.is_available())
        text = result["text"].strip()
        transcription_entry = {
            "Path": file_path,
            "Time": file_data.get("TimeAdded", datetime.now().isoformat()),
            "Duration": round(duration, 2),
            "Text": text
        }
        append_transcription(date_obj, transcription_entry)
        update_status(state_file_path, file_path, "processed")
        log(f"Completed: '{text[:30]}...'")
    except Exception as e:
        log(f"Transcription Error: {e}")
        update_status(state_file_path, file_path, "error")
    finally:
        if os.path.exists(clean_path): os.remove(clean_path)

def scan_and_process(model):
    for i in range(8): 
        scan_date = datetime.now() - timedelta(days=i)
        state_file_path = os.path.join(STATE_DIR, scan_date.strftime('%Y'), scan_date.strftime('%m'), f"{scan_date.strftime('%d')}.json")
        if not os.path.exists(state_file_path): continue
        state_data = load_json(state_file_path)
        if state_data is None: continue # Skip if read failed

        for path, info in state_data.items():
            if info.get("status") == "queue":
                process_file(model, path, info, state_file_path, scan_date)
                return True 
    return False

def main():
    log("--- CyRide Transcriber Starting ---")
    wait_for_mount()
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"Loading Whisper Model ({WHISPER_MODEL_SIZE}) on {device}...")
    try:
        model = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
        log("Model Loaded. Starting Loop...")
        while True:
            try:
                if not scan_and_process(model): time.sleep(5)
            except KeyboardInterrupt: break
            except Exception as e: 
                log(f"Error: {e}")
                time.sleep(5)
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
