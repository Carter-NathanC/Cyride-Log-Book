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
SAMPLE_RATE = 16000 # Whisper expects 16k
# Model options: tiny, base, small, medium, large
# 'medium.en' is a great balance for English radio accuracy
WHISPER_MODEL_SIZE = "medium.en" 

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

class AudioCleaner:
    @staticmethod
    def clean_audio(input_path):
        """
        Cleans radio audio:
        1. Loads MP3
        2. Bandpass filter (300Hz - 3400Hz) for voice clarity
        3. Normalization
        Returns: Path to temporary cleaned WAV file
        """
        try:
            audio = AudioSegment.from_file(input_path)
            
            # 1. Resample to 16k for Whisper/Processing
            audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(1)
            
            # 2. Bandpass Filter (300Hz - 3.4kHz) - Standard Voice Band
            # Simple implementation using pydub's high/low pass
            audio = audio.high_pass_filter(300).low_pass_filter(3400)
            
            # 3. Normalize
            audio = audio.normalize()

            # Export temp file
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
    # atomic write approach not strictly used here, but we re-read before write in main logic
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

def append_transcription(date_obj, entry):
    """Appends the transcription entry to the daily transcript list."""
    # Path: Transcriptions/YYYY/MM/DD.json
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
                else:
                    # If it was initialized differently, wrap it or start new
                    current_data = [] 
        except:
            pass
            
    current_data.append(entry)
    
    save_json(path, current_data)
    log(f"Saved transcription to {path}")

def update_status(state_file_path, file_key, new_status):
    """
    Updates the status of a file in the state JSON.
    Re-reads the file immediately before writing to minimize race conditions.
    """
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
    
    # Update state to Processing
    update_status(state_file_path, file_path, "processing")
    
    # 1. Clean Audio
    clean_path, duration = AudioCleaner.clean_audio(file_path)
    if not clean_path:
        update_status(state_file_path, file_path, "error")
        return

    try:
        # 2. Transcribe
        # fp16=False allows running on CPU if GPU not available
        result = model.transcribe(clean_path, fp16=torch.cuda.is_available())
        text = result["text"].strip()
        
        # 3. Create Record
        transcription_entry = {
            "Path": file_path,
            "Time": file_data.get("TimeAdded", datetime.now().isoformat()),
            "Duration": round(duration, 2),
            "Text": text,
            "Hash": file_data.get("Hash", "")
        }
        
        # 4. Save Transcription
        append_transcription(date_obj, transcription_entry)
        
        # 5. Update State
        update_status(state_file_path, file_path, "processed")
        log(f"Completed: '{text[:30]}...'")

    except Exception as e:
        log(f"Transcription Error: {e}")
        update_status(state_file_path, file_path, "error")
    finally:
        # Cleanup temp file
        if os.path.exists(clean_path):
            os.remove(clean_path)

def scan_and_process(model):
    # Scan today, then look back a few days if today is empty
    # to catch up on any backlog
    found_any = False
    
    for i in range(8): # Today + past 7 days
        scan_date = datetime.now() - timedelta(days=i)
        
        state_file_path = os.path.join(
            STATE_DIR,
            scan_date.strftime('%Y'),
            scan_date.strftime('%m'),
            f"{scan_date.strftime('%d')}.json"
        )
        
        if not os.path.exists(state_file_path):
            continue
            
        # Load state
        state_data = load_json(state_file_path)
        
        # Find FIRST 'queue' item
        # We process one at a time to keep loop responsive
        for path, info in state_data.items():
            if info.get("status") == "queue":
                found_any = True
                process_file(model, path, info, state_file_path, scan_date)
                # Break after one file to allow state reloading/checks
                return True 
                
    return found_any

def main():
    log("--- CyRide Transcriber Starting ---")
    
    # Check for GPU
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
            # If we processed something, don't sleep (go immediately to next)
            # If we found nothing, sleep 5 seconds
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
