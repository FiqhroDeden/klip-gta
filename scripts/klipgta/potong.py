"""Satu momen jadi satu klip 9:16: unduh potongannya, selaraskan dengan audio stream, cari facecam, caption per kata
bahasa Indonesia, bar judul di sambungan, loudness -14 LUFS."""
import json
import os
import re
import shutil
import subprocess

import numpy as np

from .transkrip import kata_whisper
from .unduh import potongan
from .util import ROOT, aman_judul, hms, run, say, sensor, slug

W, H = 1080, 1920
CAM_H = 760                 # tinggi panel facecam (atas)
GAME_H = H - CAM_H          # panel gameplay (bawah)


# --------------------------------------------------------------------------- penyelarasan
def _pcm(path, ss=None, t=None, sr=8000):
    cmd = ["ffmpeg", "-v", "error"]
    if ss is not None:
        cmd += ["-ss", f"{max(0, ss):.3f}"]
    if t is not None:
        cmd += ["-t", f"{t:.3f}"]
    cmd += ["-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def selaraskan(audio_full, raw, kira, sr=8000):
    """Detik di stream tempat potongan video dimulai. yt-dlp memotong di keyframe, jadi bisa meleset
    beberapa detik dari yang diminta; dicocokkan lewat korelasi silang audio."""
    clip = _pcm(raw, 0, 12, sr)
    if len(clip) < sr * 3:
        return kira, 0.0
    lo = kira - 8
    ref = _pcm(audio_full, lo, 12 + 16, sr)
    if len(ref) < len(clip):
        return kira, 0.0
    a = (clip - clip.mean()) / (clip.std() + 1e-9)
    b = (ref - ref.mean()) / (ref.std() + 1e-9)
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    cc = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)[: len(b) - len(a) + 1]
    k = int(np.argmax(cc))
    kuat = float(cc[k] / len(a))
    return max(0.0, lo) + k / sr, kuat


# --------------------------------------------------------------------------- facecam
def cari_wajah(raw, mulai, durasi):
    """Wajah yang muncul konsisten di beberapa frame -> (x, y, w, h, lebar_frame, tinggi_frame) atau None."""
    import cv2
    cas = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    cap = cv2.VideoCapture(raw)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    Wf, Hf = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    boxes = []
    for i in range(12):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((mulai + durasi * (i + 0.5) / 12) * fps))
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        f = cas.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6, minSize=(max(24, Wf // 40), max(24, Wf // 40)))
        if len(f):
            boxes.append(max(f, key=lambda b: b[2] * b[3]))
    cap.release()
    if len(boxes) < 5:
        return None, (Wf, Hf)
    arr = np.array(boxes, float)
    med = np.median(arr, axis=0)
    # konsisten: sebagian besar kotak dekat median (facecam tidak pindah-pindah)
    dekat = np.sum(np.abs(arr[:, 0] - med[0]) + np.abs(arr[:, 1] - med[1]) < med[2] * 0.8)
    if dekat < 5:
        return None, (Wf, Hf)
    return tuple(int(v) for v in med), (Wf, Hf)


def tata_letak(wajah, ukuran, paksa="auto"):
    """'cam' (facecam atas, gameplay bawah), 'wajah' (wajah besar, crop 9:16), atau 'penuh' (gambar utuh + blur)."""
    Wf, Hf = ukuran
    if paksa != "auto":
        return paksa
    if not wajah:
        return "penuh"
    x, y, w, h = wajah
    if w > Wf * 0.18:
        return "wajah"
    return "cam"


def _genap(v):
    return int(v) // 2 * 2


def filter_video(layout, wajah, ukuran):
    Wf, Hf = ukuran
    if layout == "cam":
        x, y, w, h = wajah
        cw = min(Wf * 0.5, max(Wf * 0.16, w * 3.4))
        ch = cw * CAM_H / W
        cx = min(max(0, x + w / 2 - cw / 2), Wf - cw)
        cy = min(max(0, y + h * 0.65 - ch / 2), Hf - ch)
        gw = min(Wf, Hf * W / GAME_H)
        gx = (Wf - gw) / 2
        return (f"[0:v]split=2[a][b];[a]crop={_genap(cw)}:{_genap(ch)}:{_genap(cx)}:{_genap(cy)},scale={W}:{CAM_H}[cam];"
                f"[b]crop={_genap(gw)}:{_genap(Hf)}:{_genap(gx)}:0,scale={W}:{GAME_H}[game];[cam][game]vstack[v0]")
    if layout == "wajah":
        x, y, w, h = wajah
        cw = min(Wf, Hf * 9 / 16)
        cx = min(max(0, x + w / 2 - cw / 2), Wf - cw)
        return f"[0:v]crop={_genap(cw)}:{_genap(Hf)}:{_genap(cx)}:0,scale={W}:{H}[v0]"
    return (f"[0:v]split=2[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5,"
            f"eq=brightness=-0.12[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2+60[v0]")


# --------------------------------------------------------------------------- caption ASS
def _ass_waktu(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def tulis_ass(path, kata, durasi, judul, kredit, layout):
    cap_y = 1250 if layout in ("cam", "wajah") else 1380
    hook_y = CAM_H if layout == "cam" else 330
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Anton,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,7,2,5,60,60,0,1
Style: Hook,Anton,86,&H00141414,&H00141414,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,1,0,3,20,0,5,70,70,0,1
Style: Kredit,Inter,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,1,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if judul:
        teks = "\\N".join(_esc(p) for p in judul.split("\n"))
        ev.append(f"Dialogue: 2,{_ass_waktu(0)},{_ass_waktu(durasi)},Hook,,0,0,0,,{{\\an5\\pos(540,{hook_y})}}{teks}")
    if kredit:
        ky = CAM_H - 40 if layout == "cam" else 1560
        ev.append(f"Dialogue: 1,{_ass_waktu(0)},{_ass_waktu(durasi)},Kredit,,0,0,0,,{{\\an1\\pos(36,{ky})}}{_esc(kredit)}")
    # kelompok kata: maksimal 3 kata, putus di jeda > 0,45 dtk; kata yang sedang diucapkan kuning
    grup, cur = [], []
    for k in kata:
        if cur and (len(cur) >= 3 or k["t"] - cur[-1]["e"] > 0.45):
            grup.append(cur); cur = []
        cur.append(k)
    if cur:
        grup.append(cur)
    for gi, g in enumerate(grup):
        akhir_grup = min(g[-1]["e"] + 0.25, grup[gi + 1][0]["t"] if gi + 1 < len(grup) else durasi)
        for wi, k in enumerate(g):
            a = k["t"]
            b = g[wi + 1]["t"] if wi + 1 < len(g) else akhir_grup
            if b <= a:
                continue
            teks = " ".join(("{\\c&H00E6FF&}" + _esc(x["w"].upper()) + "{\\c&HFFFFFF&}") if j == wi else _esc(x["w"].upper())
                            for j, x in enumerate(g))
            pop = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            ev.append(f"Dialogue: 0,{_ass_waktu(a)},{_ass_waktu(b)},Cap,,0,0,0,,{{\\an5\\pos(540,{cap_y})}}{pop}{teks}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")


def _bungkus(judul, n=30):
    """Judul jadi maksimal 2 baris seimbang."""
    kata = judul.split()
    if len(judul) <= n or len(kata) < 3:
        return judul
    best, bi = 1e9, 1
    for i in range(1, len(kata)):
        a, b = " ".join(kata[:i]), " ".join(kata[i:])
        if abs(len(a) - len(b)) < best:
            best, bi = abs(len(a) - len(b)), i
    return " ".join(kata[:bi]) + "\n" + " ".join(kata[bi:])


EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def judul_video(judul):
    """Judul yang dibakar ke video: satu baris rapi tanpa emoji (font video tidak punya emoji; emoji tetap di
    POSTING.md)."""
    return " ".join(EMOJI.sub("", judul).split())


# --------------------------------------------------------------------------- satu klip
def buat_klip(info, momen, nomor, audio_full, kerja, keluar, model_teks="large-v3-turbo", layout_paksa="auto",
              cookies=None, sensor_kata=True, kredit=True, caption="streamer"):
    s, e = float(momen["mulai_s"]), float(momen["selesai_s"])
    durasi = e - s
    nama = f"{nomor:02d}_{slug(aman_judul(momen.get('judul', '')), 40)}"
    kdir = os.path.join(kerja, f"klip{nomor:02d}")
    os.makedirs(kdir, exist_ok=True)
    say(f"[klip {nomor}] {momen.get('judul', '')}  ({hms(s)}, {int(durasi)} dtk)")
    raw, t0 = potongan(info["url"], s - 4, e + 4, os.path.join(kdir, "sumber.mp4"), cookies, audio_full=audio_full)
    if t0 is not None:                           # unduh per segmen: audio dari stream yang sama, waktunya pasti
        mulai_raw, kuat = t0, 1.0
    else:
        mulai_raw, kuat = selaraskan(audio_full, raw, s - 4)
    off = s - mulai_raw                          # detik di dalam sumber.mp4 tempat klip mulai
    if kuat < 0.25:
        say(f"  penyelarasan lemah ({kuat:.2f}); waktu bisa meleset sekitar 1 detik")
        off = 4.0
    wajah, ukuran = cari_wajah(raw, off, durasi)
    # facecam stream tidak pindah: posisi yang ketemu di satu klip dipakai lagi di klip lain (adegan gelap,
    # streamer menunduk, cutscene)
    simpan = os.path.join(kerja, "facecam.json")
    if wajah and tata_letak(wajah, ukuran) == "cam":
        with open(simpan, "w") as fh:
            json.dump({"wajah": list(wajah), "ukuran": list(ukuran)}, fh)
    elif not wajah and os.path.exists(simpan):
        d = json.load(open(simpan))
        if tuple(d["ukuran"]) == tuple(ukuran):
            wajah = tuple(d["wajah"])
            say("  wajah tidak terlihat di klip ini; pakai posisi facecam dari klip lain")
    layout = tata_letak(wajah, ukuran, layout_paksa)
    say(f"  tata letak: {layout}" + (f" (wajah {wajah[2]}px di {wajah[0]},{wajah[1]})" if wajah else ""))
    # caption: transkrip ulang potongan ini dengan model yang lebih besar (akurat per kata)
    wav = os.path.join(kdir, "suara.wav")
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.3f}", "-t", f"{durasi:.3f}", "-i", raw, "-vn", "-ac", "1",
         "-ar", "16000", wav])
    kata = kata_whisper(wav, model=model_teks, info_tiap=10 ** 9, cek_bahasa=True)
    if caption == "streamer":                    # dialog game (bahasa Inggris) tidak jadi caption besar
        kata = [k for k in kata if k.get("l") != "en"]
    if sensor_kata:
        for k in kata:
            k["w"] = sensor(k["w"])
    fonts = os.path.join(kdir, "fonts")
    if not os.path.isdir(fonts):
        shutil.copytree(os.path.join(ROOT, "assets", "fonts"), fonts)
    judul = _bungkus(judul_video(aman_judul(momen.get("judul", ""))), 26)
    tulis_ass(os.path.join(kdir, "klip.ass"), kata, durasi, judul,
              f"{info['kanal']} · live {hms(s)}" if kredit else "", layout)
    fc = filter_video(layout, wajah, ukuran) + ";[v0]ass=klip.ass:fontsdir=fonts[v];[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    os.makedirs(keluar, exist_ok=True)
    out = os.path.join(keluar, nama + ".mp4")
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.3f}", "-t", f"{durasi:.3f}", "-i", "sumber.mp4",
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
         os.path.abspath(out)], cwd=kdir)
    return {"file": out, "layout": layout, "kata": " ".join(k["w"] for k in kata), "selaras": round(kuat, 2)}
