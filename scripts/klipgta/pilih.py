"""Claude membaca transkrip per bagian (dengan tanda KERAS dan CHAT) dan memilih momen yang layak jadi klip.
Memakai langganan Claude milik pengguna lewat `claude -p` (tanpa API key)."""
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .sinyal import BIN, tanda
from .util import aman_judul, hms, parse_hms, say

PROMPT = """Kamu editor klip untuk TikTok, Reels dan YouTube Shorts di Indonesia.
Di bawah ini potongan transkrip siaran live "{judul}" dari {kanal} (game: {game}), menit {a} sampai {b}.
Setiap baris: [jam:menit:detik] ucapan streamer. Tanda [KERAS +n] = streamer tiba-tiba keras (teriak, kaget),
[CHAT xn ...] = chat meledak (n = seberapa jauh di atas biasanya, lalu contoh pesannya).

Pilih paling banyak {per} momen yang paling layak jadi klip 15-45 detik. Yang dicari:
- reaksi pertama atau kaget besar, temuan gila, kegagalan lucu, kejadian chaos, pendapat yang bikin orang mau debat;
- momen yang bisa dimengerti tanpa menonton sebelumnya (ada pembuka singkat, lalu puncaknya);
- tanda KERAS dan CHAT membantu, tapi isi ucapan yang menentukan.
Jangan pilih: sapaan, baca donasi, iklan/sponsor, menunggu loading, masalah teknis, momen 18+, SARA,
atau yang isinya hanya umpatan.

Aturan waktu: "mulai" sedikit sebelum pembuka (bukan di tengah kalimat), "selesai" tepat setelah puncak atau punchline.
Nama game tulis sesuai siarannya ({game}), jangan menebak judul lain.

Tulis judul hook dan caption dalam bahasa Indonesia santai (pakai "kamu"/gaya chat, bukan bahasa baku),
singkat, sebut nama streamer, tanpa kata kasar dan tanpa kata "mati". Judul maksimal 2 baris pendek (total <= 60 huruf),
boleh 1 emoji di akhir. Caption 1-2 kalimat dan diakhiri pertanyaan yang gampang dijawab di komentar.

Balas HANYA JSON (tanpa teks lain), daftar objek:
[{{"mulai": "h:mm:ss", "selesai": "h:mm:ss", "jenis": "reaksi|lucu|temuan|gagal|pendapat|aksi",
  "judul": "...", "caption": "...", "hashtag": ["..."], "alasan": "satu kalimat", "skor": 1-100}}]
Kalau tidak ada yang layak, balas [].

TRANSKRIP:
{teks}
"""


def _bagian(kata, sig, a, b):
    """Transkrip [a, b) dikelompokkan per 15 detik dengan tanda sinyal."""
    lines = []
    t = a
    while t < b:
        ws = [k["w"] for k in kata if t <= k["t"] < t + 15]
        marks = " ".join(m for m in (tanda(sig, int((t + d) // BIN)) for d in (0, 5, 10)) if m)
        if ws or marks:
            lines.append(f"[{hms(t)}] {' '.join(ws)} {marks}".rstrip())
        t += 15
    return "\n".join(lines)


def _tanya(prompt, model=None, timeout=420):
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("Claude Code (perintah 'claude') tidak ditemukan.")
    cmd = [claude, "-p", "Ikuti instruksi di input dan balas hanya JSON.", "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    txt = p.stdout.strip()
    m = re.search(r"\[.*\]", txt, re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except ValueError:
        return []


def pilih(info, kata, sig, kerja, jumlah=3, paralel=4, model=None, game="GTA", panjang_bagian=600, redo=False):
    path = os.path.join(kerja, "pilihan.json")
    if os.path.exists(path) and not redo:
        with open(path, encoding="utf-8") as f:
            semua = json.load(f)
    else:
        dur = info["durasi"] or (kata[-1]["t"] if kata else 0)
        mulai = 240.0 if dur > 1800 else 0.0          # lewati sapaan pembuka
        akhir = max(mulai + 60, dur - 90)             # lewati pamit
        potong = []
        t = mulai
        while t < akhir:
            potong.append((t, min(akhir, t + panjang_bagian)))
            t += panjang_bagian
        say(f"Claude membaca {len(potong)} bagian stream, {paralel} sekaligus ...")

        def kerja1(ab):
            a, b = ab
            teks = _bagian(kata, sig, a, b)
            if len(teks) < 200:
                return []
            pr = PROMPT.format(judul=info["judul"], kanal=info["kanal"], game=game, a=hms(a), b=hms(b),
                               per=max(2, jumlah), teks=teks)
            try:
                hasil = _tanya(pr, model)
            except subprocess.TimeoutExpired:
                say(f"  bagian {hms(a)} kelamaan, dilewati")
                return []
            out = []
            for h in hasil:
                try:
                    s, e = parse_hms(h["mulai"]), parse_hms(h["selesai"])
                except (KeyError, ValueError):
                    continue
                if not (a - 30 <= s < e <= b + 60) or not (10 <= e - s <= 75):
                    continue
                h["mulai_s"], h["selesai_s"] = s, e
                h["skor"] = int(h.get("skor") or 0)
                out.append(h)
            return out

        with ThreadPoolExecutor(paralel) as ex:
            semua = [h for part in ex.map(kerja1, potong) for h in part]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(semua, f, ensure_ascii=False, indent=1)
    # yang terbaik, tidak tumpang tindih, berjarak minimal 60 detik
    semua.sort(key=lambda h: -h["skor"])
    pilihan = []
    for h in semua:
        if all(h["selesai_s"] + 60 < p["mulai_s"] or h["mulai_s"] > p["selesai_s"] + 60 for p in pilihan):
            h["judul"] = " ".join(aman_judul(h.get("judul", "")).split())
            h["caption"] = aman_judul(h.get("caption", ""))
            pilihan.append(h)
        if len(pilihan) >= jumlah:
            break
    say(f"terpilih {len(pilihan)} dari {len(semua)} calon momen")
    return pilihan
