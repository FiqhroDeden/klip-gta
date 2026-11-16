"""Mencari stream dan mengunduh bagian yang perlu saja: info, audio, chat replay, subtitle otomatis, potongan video."""
import glob
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from .util import ROOT, HOME, cookies_args, run, say, ytdlp, hms


# --------------------------------------------------------------------------- cari
PENCARIAN = ["GTA 6 live indonesia", "live GTA 6 bahasa indonesia", "GTA VI live indo"]


def daftar_streamer():
    """Daftar pantau: ~/klip-gta/streamer.txt (dibuat dari bawaan skill saat pertama dipakai)."""
    mine = os.path.join(HOME, "streamer.txt")
    if not os.path.exists(mine):
        os.makedirs(HOME, exist_ok=True)
        with open(os.path.join(ROOT, "streamer.txt"), encoding="utf-8") as src, open(mine, "w", encoding="utf-8") as dst:
            dst.write(src.read())
    out = []
    with open(mine, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
    return out


def _flat(url_or_search, n, cookies=None):
    p = subprocess.run(ytdlp("--flat-playlist", "--playlist-end", str(n), "-J", *cookies_args(cookies), url_or_search),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not p.stdout.strip():
        return []
    return json.loads(p.stdout).get("entries") or []


def cari_stream(jumlah=5, jam=36, cookies=None, kata="GTA"):
    """Stream terbesar yang sedang/baru live: pencarian YouTube + daftar pantau. Satu per streamer."""
    say("mencari stream GTA terbesar (YouTube + daftar pantau) ...")
    calon = []
    for q in PENCARIAN:
        for e in _flat(f"ytsearch15:{q}", 15, cookies):
            calon.append(e)
    for ch in daftar_streamer():
        url = ch if ch.startswith("http") else f"https://www.youtube.com/{ch.lstrip('/')}"
        for e in _flat(url.rstrip("/") + "/streams", 4, cookies):
            calon.append(e)
    seen, out = set(), []
    for e in calon:
        judul = e.get("title") or ""
        if kata.lower() not in judul.lower():
            continue
        dur = e.get("duration") or 0
        live = e.get("live_status") in ("is_live", "was_live") or (dur and dur > 1800)
        if not live:
            continue
        kanal = e.get("channel") or e.get("uploader") or "?"
        if kanal in seen:
            continue
        seen.add(kanal)
        out.append({"url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id')}", "kanal": kanal,
                    "judul": judul, "durasi": dur, "view": e.get("view_count") or 0,
                    "live": e.get("live_status") == "is_live"})
    out.sort(key=lambda x: -(x["view"] or 0))
    return out[:jumlah]


# --------------------------------------------------------------------------- info
def info(url, cookies=None):
    p = run(ytdlp("-J", "--no-playlist", *cookies_args(cookies), url), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()[-1:] or ["?"]
        hint = " Coba tambahkan --cookies chrome (login YouTube di browser)." if "age" in err[0].lower() or "sign in" in err[0].lower() else ""
        raise SystemExit(f"Tidak bisa membaca info video: {err[0]}{hint}")
    d = json.loads(p.stdout)
    return {"id": d.get("id"), "judul": d.get("title") or "", "kanal": d.get("channel") or d.get("uploader") or "",
            "durasi": float(d.get("duration") or 0), "live": d.get("live_status"), "url": d.get("webpage_url") or url,
            "situs": d.get("extractor_key") or "", "subs": sorted((d.get("automatic_captions") or {}).keys()),
            "chat": "live_chat" in (d.get("subtitles") or {})}


# --------------------------------------------------------------------------- audio
def audio(url, kerja, cookies=None, bagian=None):
    """Audio saja. bagian=(a, b) detik: hanya rentang itu (stream 24 jam)."""
    for f in glob.glob(os.path.join(kerja, "audio.*")):
        if not f.endswith(".part"):
            return f
    cmd = ytdlp("-f", "bestaudio[ext=m4a]/bestaudio/worst", "--no-playlist", "-o", os.path.join(kerja, "audio.%(ext)s"),
                *cookies_args(cookies))
    if bagian:
        cmd += ["--download-sections", f"*{int(bagian[0])}-{int(bagian[1])}"]
    run(cmd + [url], capture_output=True)
    hasil = [f for f in glob.glob(os.path.join(kerja, "audio.*")) if not f.endswith(".part")]
    if not hasil:
        raise SystemExit("Audio gagal diunduh.")
    return hasil[0]


# --------------------------------------------------------------------------- subtitle otomatis YouTube
def subtitle_youtube(url, kerja, bahasa="id", cookies=None):
    """Subtitle otomatis YouTube (json3, ada waktu per kata). Cepat dan gratis; kalau tidak ada, None."""
    path = os.path.join(kerja, "yt-subs.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    run(ytdlp("--skip-download", "--no-playlist", "--write-auto-subs", "--sub-langs", f"{bahasa}-orig,{bahasa}",
              "--sub-format", "json3", "-o", os.path.join(kerja, "yt"), *cookies_args(cookies), url),
        capture_output=True, check=False)
    files = sorted(glob.glob(os.path.join(kerja, "yt.*.json3")), key=lambda f: ("orig" not in f, f))
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        data = json.load(f)
    kata = []
    for ev in data.get("events") or []:
        t0 = (ev.get("tStartMs") or 0) / 1000
        for seg in ev.get("segs") or []:
            txt = (seg.get("utf8") or "").strip()
            if txt and txt != "\n":
                kata.append({"t": round(t0 + (seg.get("tOffsetMs") or 0) / 1000, 2), "w": txt})
    kata.sort(key=lambda k: k["t"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(kata, f, ensure_ascii=False)
    return kata


# --------------------------------------------------------------------------- chat replay
def chat_youtube(url, kerja, batas_menit=25, cookies=None):
    """Chat replay YouTube -> [(detik, teks)]. Diambil halaman demi halaman (lambat untuk stream panjang),
    jadi dibatasi waktunya; yang sudah terunduh tetap dipakai."""
    raw = os.path.join(kerja, "chat.live_chat.json")
    done = os.path.join(kerja, "chat.done")
    if not os.path.exists(done):
        p = subprocess.Popen(ytdlp("--skip-download", "--no-playlist", "--write-subs", "--sub-langs", "live_chat",
                                   "-o", os.path.join(kerja, "chat"), *cookies_args(cookies), url),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=batas_menit * 60)
            open(done, "w").close()
        except subprocess.TimeoutExpired:
            p.kill()
            say(f"chat replay dihentikan setelah {batas_menit} menit (dipakai sebagian)")
    src = raw if os.path.exists(raw) else raw + ".part"
    if not os.path.exists(src):
        return []
    out = []
    with open(src, encoding="utf-8", errors="replace") as f:
        for line in f:
            out.extend(_chat_line(line))
    return sorted(out)


def _chat_line(line):
    try:
        d = json.loads(line)
    except ValueError:
        return []
    rep = d.get("replayChatItemAction") or {}
    try:
        t = int(rep.get("videoOffsetTimeMsec")) / 1000.0
    except (TypeError, ValueError):
        return []
    out = []
    for a in rep.get("actions") or []:
        item = (a.get("addChatItemAction") or {}).get("item") or {}
        msg = (item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer") or {}).get("message")
        if not msg:
            continue
        parts = []
        for r in msg.get("runs") or []:
            if "text" in r:
                parts.append(r["text"])
            elif "emoji" in r:
                parts.append(" " + ((r["emoji"].get("shortcuts") or [""])[0]) + " ")
        out.append((t, "".join(parts).strip()))
    return out


# --------------------------------------------------------------------------- potongan video
def _ambil(u, headers, a, b, coba=4):
    """Byte a..b (inklusif) dari URL, dengan Range dan beberapa kali coba."""
    import urllib.request
    for i in range(coba):
        try:
            req = urllib.request.Request(u, headers={**headers, "Range": f"bytes={a}-{b}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) == b - a + 1:
                return data
        except Exception:
            pass
        time.sleep(1 + i * 2)
    raise IOError(f"byte {a}-{b} gagal diunduh")


def _kotak(buf, pos):
    """(jenis, ukuran) kotak MP4 di posisi pos."""
    size = int.from_bytes(buf[pos:pos + 4], "big")
    kind = buf[pos + 4:pos + 8].decode("latin-1")
    if size == 1:
        size = int.from_bytes(buf[pos + 8:pos + 16], "big")
    return kind, size


def _sidx(u, headers):
    """Baca ftyp+moov dan indeks segmen (sidx) video DASH: (init_bytes, [(t_mulai, durasi, byte_a, byte_b)])."""
    buf = _ambil(u, headers, 0, 256 * 1024 - 1)
    pos, init_end, sidx = 0, None, None
    while pos + 8 <= len(buf):
        kind, size = _kotak(buf, pos)
        if kind == "moov":
            init_end = pos + size
        if kind == "sidx":
            if pos + size > len(buf):
                buf += _ambil(u, headers, len(buf), pos + size - 1)
            sidx = (pos, size)
            break
        if kind in ("moof", "mdat") or size < 8:
            break
        pos += size
    if not init_end or not sidx:
        return None
    p, size = sidx
    d = buf[p + 8:p + size]
    ver = d[0]
    timescale = int.from_bytes(d[8:12], "big")
    if ver == 0:
        t, first, q = int.from_bytes(d[12:16], "big"), int.from_bytes(d[16:20], "big"), 20
    else:
        t, first, q = int.from_bytes(d[12:20], "big"), int.from_bytes(d[20:28], "big"), 28
    n = int.from_bytes(d[q + 2:q + 4], "big")
    q += 4
    off = p + size + first
    segs = []
    for _ in range(n):
        ref = int.from_bytes(d[q:q + 4], "big") & 0x7FFFFFFF
        dur = int.from_bytes(d[q + 4:q + 8], "big")
        segs.append((t / timescale, dur / timescale, off, off + ref - 1))
        t, off, q = t + dur, off + ref, q + 12
    return buf[:init_end], segs


def _potongan_dash(url, a, b, out, audio_full, cookies, tinggi):
    """YouTube: unduh hanya segmen video yang menutupi a..b lewat indeks sidx, lalu gabung dengan audio stream yang
    sudah ada di komputer. ffmpeg 8 membaca file DASH dari awal untuk melompat ke tengah, yang di stream panjang
    bisa makan berjam-jam; ini cuma beberapa puluh MB. Kembali: detik di stream tempat out dimulai, atau None."""
    fmt = f"bv*[height<={tinggi}][vcodec^=avc1][protocol^=http]/bv*[height<={tinggi}][ext=mp4][protocol^=http]"
    r = run(ytdlp("-f", fmt, "-j", "--no-playlist", *cookies_args(cookies), url), capture_output=True, text=True,
            check=False, timeout=180)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    f = json.loads(r.stdout)
    u, headers = f.get("url"), f.get("http_headers") or {}
    if not u or "m3u8" in (f.get("protocol") or ""):
        return None
    idx = _sidx(u, headers)
    if not idx:
        return None
    init, segs = idx
    pilih = [s for s in segs if s[0] + s[1] > a and s[0] < b]
    if not pilih:
        return None
    t0 = pilih[0][0]
    bagian, x, akhir = [], pilih[0][2], pilih[-1][3]       # per 8 MB, 4 sekaligus
    while x <= akhir:
        y = min(akhir, x + 8 * 1024 * 1024 - 1)
        bagian.append((x, y))
        x = y + 1
    with ThreadPoolExecutor(4) as ex:
        isi = list(ex.map(lambda r_: _ambil(u, headers, *r_), bagian))
    frag = out + ".video.mp4"
    with open(frag, "wb") as fh:
        fh.write(init)
        for blok in isi:
            fh.write(blok)
    dur = pilih[-1][0] + pilih[-1][1] - t0
    run(["ffmpeg", "-v", "error", "-y", "-i", frag, "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", audio_full,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out])
    os.remove(frag)
    return t0


def potongan(url, a, b, out, cookies=None, tinggi=1080, audio_full=None):
    """Hanya rentang a-b dari videonya (dengan sedikit cadangan), H.264 bila ada.
    Kembali (path, t0): t0 = detik di stream tempat file mulai bila pasti diketahui, kalau tidak None."""
    meta = out + ".t0"
    if os.path.exists(out):
        return out, (float(open(meta).read()) if os.path.exists(meta) else None)
    if audio_full and os.path.exists(audio_full):
        try:
            t0 = _potongan_dash(url, a, b, out, audio_full, cookies, tinggi)
            if t0 is not None and os.path.exists(out):
                with open(meta, "w") as fh:
                    fh.write(f"{t0:.3f}")
                return out, t0
        except Exception as e:  # jatuh ke cara biasa
            say(f"  unduh per segmen gagal ({e}); pakai yt-dlp biasa")
    fmt = f"bv*[height<={tinggi}][vcodec^=avc1]+ba/bv*[height<={tinggi}]+ba/b[height<={tinggi}]/b"
    try:
        run(ytdlp("-f", fmt, "--no-playlist", "--download-sections", f"*{a:.2f}-{b:.2f}", "--merge-output-format",
                  "mp4", "-o", out, *cookies_args(cookies), url), capture_output=True, timeout=15 * 60)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"Potongan video {hms(a)}-{hms(b)} macet lebih dari 15 menit; coba lagi nanti.")
    if not os.path.exists(out):
        raise SystemExit(f"Potongan video {hms(a)}-{hms(b)} gagal diunduh.")
    return out, None
