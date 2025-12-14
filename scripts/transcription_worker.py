import os
import json
import time
import sys
import torch
import whisper
import numpy as np
import scipy.signal
from datetime import datetime, timedelta
from pydub import AudioSegment

# --- CONFIGURATION ---
BASE_DIR = os.getenv("CYRIDE_BASE_DIR", "/home/sdr/CYRIDE")
STATE_DIR = os.path.join(BASE_DIR, "states")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "Transcriptions")

# Audio Config
SAMPLE_RATE = 16000 
WHISPER_MODEL_SIZE = "medium.en" 

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

class AudioCleaner:
    @staticmethod
    def clean_audio(input_path):
        """
        Cleans radio audio:
        1. Loads MP3
        2. Bandpass filter (300Hz - 3400Hz)
        3. Normalization
        Returns: Path to temporary cleaned WAV file
        """
        try:
            audio = AudioSegment.from_file(input_path)
            audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(1)
            audio = audio.high_pass_filter(300).low_pass_filter(3400)
            audio = audio.normalize()

            temp_path = input_path + ".temp.wav"
            audio.export(temp_path, format="wav")
            return temp_path, audio.duration_seconds
        except Exception as e:
            log(f"Audio cleaning failed for {input_path}: {e}")
            return None, 0

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

def append_transcription(date_obj, entry):
    path = os.path.join(
        TRANSCRIPT_DIR,
        date_obj.strftime('%Y'),
        date_obj.strftime('%m'),
        f"{date_obj.strftime('%d')}.json"
    )
    
    current_data = []
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                content = json.load(f)
                if isinstance(content, list):
                    current_data = content
        except:
            pass
            
    current_data.append(entry)
    save_json(path, current_data)
    log(f"Saved transcription to {path}")

def update_status(state_file_path, file_key, new_status):
    try:
        data = load_json(state_file_path)
        if file_key in data:
            data[file_key]["status"] = new_status
            data[file_key]["TimeUpdated"] = datetime.now().isoformat()
            save_json(state_file_path, data)
            return True
    except Exception as e:
        log(f"Failed to update status for {file_key}: {e}")
    return False

def process_file(model, file_path, file_data, state_file_path, date_obj):
    log(f"Processing: {file_path}")
    update_status(state_file_path, file_path, "processing")
    
    clean_path, duration = AudioCleaner.clean_audio(file_path)
    if not clean_path:
        update_status(state_file_path, file_path, "error")
        return

    try:
        # fp16=False allows CPU usage if GPU is missing
        result = model.transcribe(clean_path, fp16=torch.cuda.is_available())
        text = result["text"].strip()
        
        transcription_entry = {
            "Path": file_path,
            "Time": file_data.get("TimeAdded", datetime.now().isoformat()),
            "Duration": round(duration, 2),
            "Text": text,
            "Hash": file_data.get("Hash", "")
        }
        
        append_transcription(date_obj, transcription_entry)
        update_status(state_file_path, file_path, "processed")
        log(f"Completed: '{text[:30]}...'")

    except Exception as e:
        log(f"Transcription Error: {e}")
        update_status(state_file_path, file_path, "error")
    finally:
        if os.path.exists(clean_path):
            os.remove(clean_path)

def scan_and_process(model):
    # Scan today + past 7 days
    found_any = False
    for i in range(8): 
        scan_date = datetime.now() - timedelta(days=i)
        
        state_file_path = os.path.join(
            STATE_DIR,
            scan_date.strftime('%Y'),
            scan_date.strftime('%m'),
            f"{scan_date.strftime('%d')}.json"
        )
        
        if not os.path.exists(state_file_path):
            continue
            
        state_data = load_json(state_file_path)
        
        # Find first item with status 'queue'
        for path, info in state_data.items():
            if info.get("status") == "queue":
                found_any = True
                process_file(model, path, info, state_file_path, scan_date)
                return True # Return to refresh loop/state
                
    return found_any

def main():
    log("--- CyRide Transcriber Starting ---")
    
    # Ensure directories exist
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"Loading Whisper Model ({WHISPER_MODEL_SIZE}) on {device}...")
    
    try:
        model = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
        log("Model Loaded Successfully.")
    except Exception as e:
        log(f"FATAL: Could not load Whisper model. {e}")
        sys.exit(1)

    log("Starting Processing Loop...")
    
    while True:
        try:
            did_work = scan_and_process(model)
            if not did_work:
                time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Critical Loop Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
