"""Narration in the same two voices as the Backstop/Continuity films, via Gemini TTS.

Voice A = Rasalgethi (the narrator), B = Aoede — the pair used across the set, so the films
sound like one hand. Emits out/vo/<n>.wav plus a manifest with measured durations, which the
mux uses to place each line and to check nothing overruns its shot.
"""
import contextlib, json, pathlib, sys, time, wave

from google import genai
from google.genai import types

HERE = pathlib.Path(__file__).parent
VO = HERE / "out" / "vo"; VO.mkdir(parents=True, exist_ok=True)
MODEL = "gemini-2.5-flash-preview-tts"
LOCATION = "us-central1"          # 'global' 500s for TTS; us-central1 works
# alternate the two voices so the film has a second presence, as the other films do
VOICE = {1: "Rasalgethi", 2: "Aoede", 3: "Rasalgethi", 4: "Aoede", 5: "Rasalgethi",
         6: "Aoede", 7: "Rasalgethi", 8: "Aoede", 9: "Rasalgethi"}

client = genai.Client(vertexai=True, location=LOCATION)
narr = json.loads((HERE / "narration.json").read_text())


def dur(p):
    with contextlib.closing(wave.open(str(p), "r")) as w:
        return w.getnframes() / w.getframerate()


def tts(text, voice, out):
    for attempt in range(4):
        try:
            r = client.models.generate_content(
                model=MODEL, contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
            data = r.candidates[0].content.parts[0].inline_data.data
            with wave.open(str(out), "wb") as w:      # Gemini returns 24kHz PCM16 mono
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(data)
            return dur(out)
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(2.0 * (attempt + 1))


manifest, over = {}, []
for k in sorted(narr, key=int):
    v = narr[k]
    p = VO / f"{k}.wav"
    d = tts(v["text"], VOICE[int(k)], p)
    room = v["until"] - v["at"]
    manifest[k] = {"file": p.name, "at": v["at"], "dur": round(d, 2), "room": round(room, 1)}
    flag = ""
    if d > room:
        over.append(k); flag = f"  OVERRUNS by {d-room:.1f}s"
    print(f"  {k}: {d:5.1f}s  (room {room:4.1f}s){flag}", flush=True)

(HERE / "out" / "vo.json").write_text(json.dumps(manifest, indent=1))
print(f"\n  {len(manifest)} lines written to {VO}")
if over:
    print(f"  lines overrunning their shot: {', '.join(over)} — tighten copy or lengthen the hold")
