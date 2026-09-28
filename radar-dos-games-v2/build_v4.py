import asyncio, json, re, shutil, subprocess
from pathlib import Path
import edge_tts

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work_v4"
OUT = ROOT / "output_v4"
ASSETS = ROOT / "assets"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ACCENT = "0x35F2C3"

for p in (WORK, OUT):
    p.mkdir(parents=True, exist_ok=True)

with open(ROOT / "episode.json", "r", encoding="utf-8") as f:
    ep = json.load(f)

CARDS = {
    "O que já sabemos": ("ESPECIAL GTA VI", "10 INFORMAÇÕES CONFIRMADAS", "Somente fontes oficiais da Rockstar"),
    "1. Data de lançamento": ("CONFIRMADO", "19 NOV 2026", "Data oficial de lançamento"),
    "2. Plataformas confirmadas": ("PLATAFORMAS", "PS5  •  XBOX SERIES X|S", "PC: sem data oficial"),
    "3. Jason e Lucia": ("PROTAGONISTAS", "JASON + LUCIA", "A dupla central da história"),
    "4. Uma conspiração criminal": ("HISTÓRIA", "CONSPIRAÇÃO EM LEONIDA", "Um golpe simples dá errado"),
    "5. Vice City voltou": ("LOCALIZAÇÃO", "VICE CITY ESTÁ DE VOLTA", "Agora dentro do estado de Leonida"),
    "6. Leonida vai além da cidade": ("MUNDO ABERTO", "VICE CITY • KEYS • GRASSRIVERS", "Port Gellhorn • Mount Kalaga • Ambrosia"),
    "7. Pré-venda já existe": ("PRÉ-VENDA", "JÁ DISPONÍVEL", "Pacote Vintage Vice City confirmado"),
    "8. Ultimate Edition confirmada": ("EDIÇÕES", "ULTIMATE EDITION", "Conteúdo adicional confirmado"),
    "9. Álbum oficial no lançamento": ("TRILHA OFICIAL", "GRAND THEFT AUTO VI: THE ALBUM", "Lançamento: 19 NOV 2026"),
    "10. Muito material oficial": ("FONTE", "ROCKSTAR GAMES", "Trailers • clipes • artes • screenshots"),
    "Radar dos Games": ("RADAR DOS GAMES", "NOTÍCIAS • LANÇAMENTOS • GAMEPLAYS", "Informação rápida, visual e com fonte"),
}


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
    text = text.replace(":", ": ").replace(";", "; ")
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        "PlayStation cinco": "PlayStation 5",
        "PlayStation quatro": "PlayStation 4",
        "Grand Theft Auto seis": "Grand Theft Auto 6",
        "GTA seis": "GTA 6",
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
        communicate = edge_tts.Communicate(
            text=humanize_text(seg["text"]), voice=voice,
            rate="-3%", volume="+0%", pitch="-2Hz",
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
    return candidates[len(used) % len(candidates)]


def make_visual(img, seconds, out_path, direction=1):
    frames = max(1, int(seconds * 30))
    xexpr = "iw/2-(iw/zoom/2)+18*sin(on/58)" if direction > 0 else "iw/2-(iw/zoom/2)-18*sin(on/58)"
    vf = (
        "scale=2200:1238:force_original_aspect_ratio=increase,"
        "crop=2200:1238,"
        f"zoompan=z='min(zoom+0.00040,1.095)':x='{xexpr}':"
        f"y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30,format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(img), "-vf", vf,
        "-t", f"{seconds:.3f}", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-pix_fmt", "yuv420p", str(out_path)
    ])


def write_text(path, text):
    path.write_text(text, encoding="utf-8")
    return path.resolve()


segment_files = []
segment_starts = []
cursor = 0.0

for idx, seg in enumerate(ep["segments"]):
    print(f"--- Segment {idx+1}/{len(ep['segments'])}: {seg['title']} ---")
    audio = audio_files[idx]
    dur = duration(audio)
    segment_starts.append(cursor)
    cursor += dur

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

    badge, main, sub = CARDS.get(seg["title"], ("RADAR DOS GAMES", seg["title"], "Informação confirmada"))
    title_file = write_text(WORK / f"seg_{idx:02d}_title.txt", seg["title"])
    badge_file = write_text(WORK / f"seg_{idx:02d}_badge.txt", badge)
    main_file = write_text(WORK / f"seg_{idx:02d}_main.txt", main)
    sub_file = write_text(WORK / f"seg_{idx:02d}_sub.txt", sub)
    number_file = write_text(WORK / f"seg_{idx:02d}_num.txt", f"{idx:02d}" if 0 < idx < 11 else "")

    seg_out = WORK / f"segment_{idx:02d}.mp4"
    fade_out = max(0.0, dur - 0.35)
    card_end = min(max(7.3, dur - 1.0), 10.5)
    if dur < 8.5:
        card_end = max(5.8, dur - 0.5)

    vf_parts = [
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.28",
        "drawbox=x=0:y=0:w=iw:h=70:color=black@0.46:t=fill",
        f"drawtext=fontfile={FONT_REG}:text='RADAR DOS GAMES':fontsize=27:fontcolor=white@0.94:x=42:y=20",
        # Topic transition: brief cinematic overlay at the start of every block.
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.46:t=fill:enable='between(t,0,1.55)'",
        f"drawbox=x=140:y=345:w=12:h=215:color={ACCENT}@0.95:t=fill:enable='between(t,0,1.55)'",
        f"drawtext=fontfile={FONT}:textfile='{title_file}':fontsize=64:fontcolor=white:x=185:y=380:enable='between(t,0,1.55)'",
        # Small topic number for list items.
        f"drawtext=fontfile={FONT}:textfile='{number_file}':fontsize=150:fontcolor={ACCENT}@0.20:x=1530:y=315:enable='between(t,0,1.55)'",
        # Badge at upper-right, reinforcing source/status/category.
        f"drawbox=x=1430:y=104:w=400:h=64:color={ACCENT}@0.90:t=fill:enable='between(t,2.2,{card_end:.2f})'",
        f"drawtext=fontfile={FONT}:textfile='{badge_file}':fontsize=27:fontcolor=black:x=1460:y=121:enable='between(t,2.2,{card_end:.2f})'",
        # Main information card.
        f"drawbox=x=84:y=710:w=1180:h=238:color=black@0.72:t=fill:enable='between(t,3.7,{card_end:.2f})'",
        f"drawbox=x=84:y=710:w=11:h=238:color={ACCENT}@0.98:t=fill:enable='between(t,3.7,{card_end:.2f})'",
        f"drawtext=fontfile={FONT}:textfile='{main_file}':fontsize=52:fontcolor=white:x=126:y=760:enable='between(t,3.7,{card_end:.2f})'",
        f"drawtext=fontfile={FONT_REG}:textfile='{sub_file}':fontsize=31:fontcolor={ACCENT}:x=128:y=850:enable='between(t,3.7,{card_end:.2f})'",
        # Persistent subtle source cue.
        f"drawtext=fontfile={FONT_REG}:text='FONTE: ROCKSTAR GAMES':fontsize=21:fontcolor=white@0.72:x=1530:y=1020",
    ]
    vf = ",".join(vf_parts)

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

final = OUT / "gta6-10-coisas-confirmadas-v4-info-rich.mp4"
run([
    "ffmpeg", "-y", "-loglevel", "error", "-i", rough,
    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final
])

# Preview begins with the release-date segment and continues through platforms, where the new visual language is clearest.
preview_start = segment_starts[1] if len(segment_starts) > 2 else 0
preview = OUT / "preview-v4-data-plataformas.mp4"
run([
    "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{preview_start:.3f}", "-i", final,
    "-t", "70", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", preview
])

shutil.copy2(audio_files[0], OUT / "amostra-voz-v4.mp3")
(OUT / "v4-info.txt").write_text(
    "V4 visual system: topic transition + category badge + key-fact card + source cue.\n"
    f"Voice: {voice_name}\nAudio mastering: -16 LUFS, light compression\n",
    encoding="utf-8"
)

print("DONE:", final)
print("VOICE:", voice_name)
print("DURATION:", duration(final))
