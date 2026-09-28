import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUT = ROOT / "output"
ASSETS = ROOT / "assets"
TOOLS = ROOT / "tools"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

for p in (WORK, OUT):
    p.mkdir(parents=True, exist_ok=True)

with open(ROOT / "episode.json", "r", encoding="utf-8") as f:
    ep = json.load(f)

PIPER = TOOLS / "piper" / "piper"
MODEL = TOOLS / "pt_BR-cadu-medium.onnx"


def run(cmd, *, input_bytes=None):
    print("RUN:", " ".join(str(x) for x in cmd))
    subprocess.run([str(x) for x in cmd], input=input_bytes, check=True)


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return float(out)


def norm(s):
    s = s.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]+", "", s)

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
    # Slow Ken Burns zoom with alternating horizontal drift.
    if direction > 0:
        xexpr = "iw/2-(iw/zoom/2)+20*sin(on/55)"
    else:
        xexpr = "iw/2-(iw/zoom/2)-20*sin(on/55)"
    vf = (
        "scale=2200:1238:force_original_aspect_ratio=increase,"
        "crop=2200:1238,"
        f"zoompan=z='min(zoom+0.00045,1.10)':x='{xexpr}':"
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
    txt_file = WORK / f"seg_{idx:02d}.txt"
    wav_file = WORK / f"seg_{idx:02d}.wav"
    txt_file.write_text(seg["text"], encoding="utf-8")

    # Piper neural Brazilian Portuguese voice. Slightly slower than default for a news/gaming narrator cadence.
    run([
        PIPER, "--model", MODEL, "--output_file", wav_file,
        "--length_scale", "1.06", "--noise_scale", "0.55", "--noise_w", "0.72"
    ], input_bytes=(seg["text"] + "\n").encode("utf-8"))

    dur = duration(wav_file)
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
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", concat_txt, "-c", "copy", visual_join
    ])

    title_file = WORK / f"seg_{idx:02d}_title.txt"
    title_file.write_text(seg["title"], encoding="utf-8")
    seg_out = WORK / f"segment_{idx:02d}.mp4"
    fade_out = max(0.0, dur - 0.35)
    vf = (
        f"fade=t=in:st=0:d=0.28,fade=t=out:st={fade_out:.3f}:d=0.28,"
        "drawbox=x=0:y=0:w=iw:h=74:color=black@0.46:t=fill,"
        f"drawtext=fontfile={FONT_REG}:text='RADAR DOS GAMES':fontsize=28:fontcolor=white@0.92:x=42:y=22,"
        "drawbox=x=70:y=h-205:w=1780:h=118:color=black@0.64:t=fill:enable='lt(t,4.5)',"
        f"drawtext=fontfile={FONT}:textfile='{title_file.resolve()}':fontsize=48:fontcolor=white:"
        "x=100:y=h-172:enable='lt(t,4.5)'"
    )
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", visual_join, "-i", wav_file,
        "-vf", vf,
        "-af", "highpass=f=70,lowpass=f=14500,acompressor=threshold=-18dB:ratio=2.2:attack=20:release=180,alimiter=limit=0.96",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest",
        "-pix_fmt", "yuv420p", seg_out
    ])
    segment_files.append(seg_out)

final_list = WORK / "final_segments.txt"
final_list.write_text("\n".join(f"file '{p.resolve()}'" for p in segment_files), encoding="utf-8")
rough = WORK / "rough.mp4"
run([
    "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
    "-i", final_list, "-c", "copy", rough
])

final = OUT / "gta6-10-coisas-confirmadas-v2.mp4"
run([
    "ffmpeg", "-y", "-loglevel", "error", "-i", rough,
    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final
])

# Thumbnail from a strong Jason/Lucia image.
thumb_img = choose("Jason_and_Lucia_01")
line1 = ep.get("thumbnail_line1", "10 COISAS")
line2 = ep.get("thumbnail_line2", "CONFIRMADAS")
thumb = OUT / "thumbnail-gta6-v2.png"
thumb_vf = (
    "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
    "drawbox=x=0:y=0:w=1280:h=720:color=black@0.18:t=fill,"
    "drawbox=x=48:y=440:w=1184:h=220:color=black@0.67:t=fill,"
    f"drawtext=fontfile={FONT}:text='{line1}':fontsize=88:fontcolor=white:x=(w-text_w)/2:y=466,"
    f"drawtext=fontfile={FONT}:text='{line2}':fontsize=94:fontcolor=0x36f5a2:x=(w-text_w)/2:y=558"
)
run([
    "ffmpeg", "-y", "-loglevel", "error", "-i", thumb_img,
    "-vf", thumb_vf, "-frames:v", "1", thumb
])

metadata = OUT / "youtube-metadata.txt"
metadata.write_text(
    "TITLE\n" + ep["title"] + "\n\nDESCRIPTION\n"
    "GTA 6 já tem muita informação confirmada oficialmente pela Rockstar. Neste vídeo, reunimos 10 pontos que você precisa saber antes do lançamento.\n\n"
    "Fontes oficiais:\n" + "\n".join(ep["sources"]) +
    "\n\n#GTA6 #GTAVI #RadarDosGames #Games\n\nTAGS\n"
    "gta 6, gta vi, gta 6 brasil, gta 6 lançamento, gta 6 confirmado, gta 6 vice city, gta 6 jason, gta 6 lucia, radar dos games",
    encoding="utf-8"
)

print("DONE:", final)
print("DURATION:", duration(final))
