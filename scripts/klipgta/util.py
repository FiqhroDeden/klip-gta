"""Hal kecil yang dipakai semua langkah: cetak, waktu, folder, perintah luar."""
import json
import os
import re
import shutil
import subprocess
import sys
import time

T0 = time.time()
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # folder skill
HOME = os.path.join(os.path.expanduser("~"), "klip-gta")
KERJA = os.path.join(HOME, "kerja")


def say(msg, who=""):
    el = int(time.time() - T0)
    tag = f"[{el // 60:02d}:{el % 60:02d}]"
    print(f"{tag} {who + ' ' if who else ''}{msg}", flush=True)


def hms(seconds):
    s = int(max(0, seconds))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_hms(text):
    """'1:02:03' / '62:03' / '3723' -> detik."""
    parts = [float(p) for p in str(text).strip().split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def slug(text, n=60):
    t = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    t = re.sub(r"[\s_]+", "-", t).strip("-")
    return (t[:n].rstrip("-")) or "klip"


def run(cmd, **kw):
    """Jalankan perintah, gagal = berhenti dengan pesan yang jelas."""
    kw.setdefault("check", True)
    try:
        return subprocess.run(cmd, **kw)
    except FileNotFoundError:
        sys.exit(f"Perintah tidak ditemukan: {cmd[0]}. Jalankan setup dulu (lihat SKILL.md).")


def ytdlp(*args):
    """yt-dlp dari environment skill ini (python -m yt_dlp), supaya versinya sama di semua mesin."""
    return [sys.executable, "-m", "yt_dlp", "--no-warnings", *args]


def cookies_args(cookies):
    return ["--cookies-from-browser", cookies] if cookies else []


def need(tool):
    if not shutil.which(tool):
        sys.exit(f"'{tool}' belum terpasang. Jalankan: python scripts/klip.py --cek")


def save_json(path, data):
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(path + ".part", path)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Kata yang di TikTok sering kena turun jangkauan atau dihapus, dan kata kasar.
# Dipakai untuk judul, caption posting, nama file, dan (sensor) teks yang dibakar.
KASAR = re.compile(
    r"\b(anjing|anjeng|bangsat|bajingan|kontol|memek|ngentot|jancok|jancuk|goblok|tolol|babi|"
    r"asu|tai|fuck\w*|shit\w*|bitch\w*|damn)\b", re.IGNORECASE)
RAWAN = re.compile(r"\b(mati|meninggal|tewas|bunuh\w*|mampus|bundir)\b", re.IGNORECASE)


def sensor(text):
    """Kata kasar jadi huruf pertama + bintang (a****), supaya tetap terbaca maksudnya."""
    return KASAR.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text)


def aman_judul(text):
    """Judul/caption/nama file: kata kasar disensor, kata rawan diganti yang aman."""
    text = sensor(text)
    ganti = {"mati": "tumbang", "meninggal": "tumbang", "tewas": "tumbang", "mampus": "habis", "bundir": "nyerah"}

    def rep(m):
        w = m.group(0).lower()
        return "habisi" if w.startswith("bunuh") else ganti.get(w, "kalah")

    return RAWAN.sub(rep, text)
