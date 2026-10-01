"""
================================================================================
KAEKAE AUDIO WORKER (TERMINAL 2: MICROPHONE & SOUND ENGINE)
================================================================================
Dedicated strictly to all audio and voice operations:
1. Listens to Camfrog room voices via VB-Audio Virtual Cable.
2. Transcribes spoken voice via Whisper STT into audio_transcripts.jsonl.
3. Detects microphone wake triggers ("kae", "kaekae", "kaebot").
4. Consumes pending_speech_queue.json to audibly broadcast via Talk button:
   - Valley Persona (CyGFgkeLSDCTZEzs6B89): Normal tones & !say
   - Uppity Persona (XDP6lUBFhYCAbkIhMCt5): !diss & roasts
   - Valley Sexy Persona (zqDzpaf3w8JdUBL9YxSv): Male interactions / flirty
5. Displays real-time audio volume VU meter and live voice transcriptions!
================================================================================
"""

import os
import sys
import time
import json
import threading

# Set terminal title
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("KaeKae Audio Engine [Terminal 2 - Voice & Virtual Cable]")
    except Exception:
        pass

print("=" * 76)
print("  KAEKAE AUDIO WORKER (TERMINAL 2: SOUND & VOICE ENGINE)")
print("=" * 76)

from cef_probe import (
    global_talk_controller,
    synthesize_speech_to_wav,
    play_wav_to_virtual_cable,
    resolve_audio_output_device,
    get_configured_output_device,
    ELEVENLABS_VOICES,
    get_elevenlabs_api_key
)

PENDING_SPEECH_FILE = "pending_speech_queue.json"
AUDIO_OUTPUT_DEVICE = get_configured_output_device()

print(f"  Target Audio Device  : '{AUDIO_OUTPUT_DEVICE}'")
api_key = get_elevenlabs_api_key()
if api_key:
    masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
    print(f"  ElevenLabs Engine    : ACTIVE (Key: {masked})")
    print(f"    - VALLEY Voice ID  : {ELEVENLABS_VOICES['valley']} (Normal/Sweet)")
    print(f"    - UPPITY Voice ID  : {ELEVENLABS_VOICES['uppity']} (Diss/Roasts)")
    print(f"    - SEXY Voice ID    : {ELEVENLABS_VOICES['valley_sexy']} (Male Flirty)")
else:
    print("  ElevenLabs Engine    : NOT DETECTED (Using Expressive Neural SSML Engine)")
    print("  To enable ElevenLabs : Add 'elevenlabs_api_key' to config.json")
print("=" * 76 + "\n")

def speech_queue_consumer_loop():
    """Continuously watches pending_speech_queue.json and speaks items on Camfrog mic."""
    print("[AUDIO WORKER] Speech queue consumer online. Watching for broadcast requests...")
    while True:
        try:
            if os.path.exists(PENDING_SPEECH_FILE) and os.path.getsize(PENDING_SPEECH_FILE) > 2:
                items = []
                try:
                    with open(PENDING_SPEECH_FILE, "r", encoding="utf-8") as f:
                        items = json.load(f)
                except Exception:
                    time.sleep(0.1)
                    continue

                if items and isinstance(items, list):
                    # Pop next speech task
                    task = items.pop(0)
                    with open(PENDING_SPEECH_FILE, "w", encoding="utf-8") as f:
                        json.dump(items, f, indent=2)

                    text = task.get("text", "").strip()
                    persona = task.get("persona", "valley")
                    voice = task.get("voice", "en-US-AvaNeural")
                    rate = task.get("rate", "+12%")
                    pitch = task.get("pitch", "+16Hz")

                    if text:
                        print(f"\n[SPEECH QUEUE] Broadcasting: \"{text}\" (Persona: {persona.upper()})...")
                        if global_talk_controller is not None:
                            global_talk_controller.speak_and_hold(
                                text,
                                voice=voice,
                                rate=rate,
                                pitch=pitch,
                                output_device=AUDIO_OUTPUT_DEVICE,
                                persona=persona
                            )
                        else:
                            temp_wav = "temp_say_broadcast.wav"
                            synthesize_speech_to_wav(text, temp_wav, voice=voice, rate=rate, pitch=pitch, persona=persona)
                            play_wav_to_virtual_cable(temp_wav, AUDIO_OUTPUT_DEVICE)
                        print(f"[SPEECH QUEUE] Broadcast finished for: \"{text}\"\n")
        except Exception as e:
            print(f"[AUDIO WORKER] Speech consumer warning: {e}")

        time.sleep(0.2)

def start_room_audio_listener():
    """Starts listening to Camfrog room audio from VB-Audio Virtual Cable."""
    try:
        import kaekae_bot
        print("[AUDIO WORKER] Initializing room microphone recorder & Whisper STT...")
        # Start queue worker in background thread
        q_thread = threading.Thread(target=speech_queue_consumer_loop, daemon=True)
        q_thread.start()

        # Start transcribe hotkey listener (Left-Ctrl + Right-Click, F8)
        if hasattr(kaekae_bot, "start_transcribe_hotkey_listener"):
            kaekae_bot.start_transcribe_hotkey_listener()

        # Run audio recorder loop
        if hasattr(kaekae_bot, "voice_listener_worker"):
            kaekae_bot.voice_listener_worker()
        elif hasattr(kaekae_bot, "audio_recorder_loop"):
            kaekae_bot.audio_recorder_loop()
        else:
            print("[AUDIO WORKER ERROR] Neither voice_listener_worker nor audio_recorder_loop found!")
            speech_queue_consumer_loop()
    except Exception as e:
        print(f"[AUDIO WORKER] Listener error: {e}")
        # If full recorder loop fails, keep queue consumer running
        speech_queue_consumer_loop()

if __name__ == "__main__":
    try:
        start_room_audio_listener()
    except KeyboardInterrupt:
        print("\n[AUDIO WORKER] Stopped by user.")
