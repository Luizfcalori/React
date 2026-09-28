import asyncio, json, os, re, shutil, subprocess
from pathlib import Path
import edge_tts

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work_v3"
OUT = ROOT / "output_v3"
ASSETS = ROOT / "assets"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

for p in (WORK, OUT):
    p.mkdir(parents=True, exist_ok=True)

with open(ROOT / "episode.json", "r", encoding="utf-8") as f:
    ep = json.load(f)


def run(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run([str(x) for x in cmd], check=True)


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return float(out)


def norm(s):
    s = s.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]+", "", s)


def humanize_text(text):
    # Extra punctuation nudges the neural narrator toward conversational pacing.
    text = text.replace(":", ": ").replace(";", "; ")
    text = re.sub(r"\s+", " ", text).strip()
    # Keep English game/brand terms exactly written so the multilingual voice can switch pronunciation.
    replacements = {
        "PlayStation cinco": "PlayStation 5",
        "PlayStation quatro": "PlayStation 4",
        "Xbox Series X e Series S": "Xbox Series X e Series S",
        "Xbox One": "Xbox One",
        "Grand Theft Auto seis": "Grand Theft Auto 6",
        "GTA seis": "GTA 6",
        "Ultimate Edition": "Ultimate Edition",
        "Vintage Vice City": "Vintage Vice City",
        "The Album": "The Album",
        "Vice City": "Vice City",
        "Leonida Keys": "Leonida Keys",
        "Port Gellhorn": "Port Gellhorn",
        "Grassrivers": "Grassrivers",
        "Mount Kalaga": "Mount Kalaga",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text


async def pick_voice():
    voices = await edge_tts.list_voices()
    names = {v.get("ShortName") for v in voices}
    prefs = [
        "pt-BR-MacerioMultilingualNeural",
        "pt-BR-ThalitaMultilingualNeural",
        "pt-BR-DonatoNeural",
        "pt-BR-FabioNeural",
        "pt-BR-AntonioNeural",
    ]
    for v in prefs:
        if v in names:
            print("VOICE:", v)
            return v
    raise RuntimeError("No preferred Brazilian Portuguese neural voice available")


async def synthesize_all():
    voice = await pick_voice()
    files = []
    for idx, seg in enumerate(ep["segments"]):
        out = WORK / f"seg_{idx:02d}.mp3"
        text = humanize_text(seg["text"])
        # Slightly relaxed cadence: natural news/gaming host, not announcer-like.
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate="-3%",
            volume="+0%",
            pitch="-2Hz",
        )
        await communicate.save(str(out))
        files.append(out)
    return voice, files


voice_name, audio_files = asyncio.run(synthesize_all())

images = [p for p in ASSETS.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
if not images:
    raise SystemExit("No GTA VI screenshots found in assets")

used = set()

def choose(keyword):
    k = norm(keyword)
    exact = [p for p in images if k in norm(p.stem)]
    candidates = exact if exact else images
    for p in candidates:
        if p not in used:
            used.add(p)
            return p
    p = candidates[len(used) % len(candidates)]
    return p


def make_visual(img, seconds, out_path, direction=1):
    frames = max(1, int(seconds * 30))
    if direction > 0:
        xexpr = "iw/2-(iw/zoom/2)+18*sin(on/58)"
    else:
        xexpr = "iw/2-(iw/zoom/2)-18*sin(on/58)"
    vf = (
        "scale=2200:1238:force_original_aspect_ratio=increase,"
        "crop=2200:1238,"
        f"zoompan=z='min(zoom+0.00040,1.095)':x='{xexpr}':"
        f"y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30,"
        "format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(img),
        "-vf", vf, "-t", f"{seconds:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", str(out_path)
    ])

segment_files = []
for idx, seg in enumerate(ep["segments"]):
    print(f"--- Segment {idx+1}/{len(ep['segments'])}: {seg['title']} ---")
    audio = audio_files[idx]
    dur = duration(audio)
    visuals = seg.get("visuals", []) or [""]
    chosen = [choose(k) for k in visuals[:3]]
    per = dur / len(chosen)
    visual_parts = []
    for j, img in enumerate(chosen):
        part = WORK / f"seg_{idx:02d}_vis_{j}.mp4"
        make_visual(img, per + 0.08, part, direction=1 if j % 2 == 0 else -1)
        visual_parts.append(part)

    concat_txt = WORK / f"seg_{idx:02d}_visuals.txt"
    concat_txt.write_text("\n".join(f"file '{p.resolve()}'" for p in visual_parts), encoding="utf-8")
    visual_join = WORK / f"seg_{idx:02d}_visual_join.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", visual_join])

    title_file = WORK / f"seg_{idx:02d}_title.txt"
    title_file.write_text(seg["title"], encoding="utf-8")
    seg_out = WORK / f"segment_{idx:02d}.mp4"
    fade_out = max(0.0, dur - 0.35)
    vf = (
        f"fade=t=in:st=0:d=0.28,fade=t=out:st={fade_out:.3f}:d=0.28,"
        "drawbox=x=0:y=0:w=iw:h=74:color=black@0.46:t=fill,"
        f"drawtext=fontfile={FONT_REG}:text='RADAR DOS GAMES':fontsize=28:fontcolor=white@0.92:x=42:y=22,"
        "drawbox=x=70:y=h-205:w=1780:h=118:color=black@0.64:t=fill:enable='lt(t,4.5)',"
        f"drawtext=fontfile={FONT}:textfile='{title_file.resolve()}':fontsize=48:fontcolor=white:x=100:y=h-172:enable='lt(t,4.5)'"
    )
    af = (
        "highpass=f=70,lowpass=f=15000,"
        "acompressor=threshold=-20dB:ratio=1.8:attack=12:release=160,"
        "loudnorm=I=-16:TP=-1.5:LRA=7,alimiter=limit=0.97"
    )
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", visual_join, "-i", audio,
        "-vf", vf, "-af", af,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
        "-pix_fmt", "yuv420p", seg_out
    ])
    segment_files.append(seg_out)

final_list = WORK / "final_segments.txt"
final_list.write_text("\n".join(f"file '{p.resolve()}'" for p in segment_files), encoding="utf-8")
rough = WORK / "rough.mp4"
run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", final_list, "-c", "copy", rough])

final = OUT / "gta6-10-coisas-confirmadas-v3-humanizado.mp4"
run([
    "ffmpeg", "-y", "-loglevel", "error", "-i", rough,
    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final
])

# Export a quick voice-only sample and 40s video preview for review.
shutil.copy2(audio_files[0], OUT / "amostra-voz-v3.mp3")
preview = OUT / "preview-v3-40s.mp4"
run([
    "ffmpeg", "-y", "-loglevel", "error", "-i", final,
    "-t", "40", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", preview
])

(OUT / "voice-info.txt").write_text(
    f"Voice: {voice_name}\nRate: -3%\nPitch: -2Hz\nAudio mastering: loudness -16 LUFS, light compression\n",
    encoding="utf-8"
)

print("DONE:", final)
print("VOICE:", voice_name)
print("DURATION:", duration(final))
