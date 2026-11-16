"""Transkrip bahasa Indonesia. Untuk memilih momen: subtitle otomatis YouTube bila ada (cepat), kalau tidak
faster-whisper. Untuk caption klip: faster-whisper model yang lebih besar, hanya pada potongan pendek (akurat
per kata). Model kecil (tiny/base) mengacaukan bahasa Indonesia, jadi tidak dipakai untuk caption."""
import os

from .util import say

_models = {}


def _model(nama):
    if nama not in _models:
        from faster_whisper import WhisperModel
        say(f"memuat Whisper '{nama}' (pertama kali: diunduh dulu)")
        _models[nama] = WhisperModel(nama, device="cpu", compute_type="int8", cpu_threads=max(2, (os.cpu_count() or 4) - 1))
    return _models[nama]


def _pcm16k(media):
    """Audio mono 16 kHz float32 lewat ffmpeg. Tidak memakai PyAV bawaan faster-whisper: versi PyAV baru
    tidak cocok dengannya (open() got an unexpected keyword argument 'metadata_errors')."""
    import subprocess
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", media, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def _gabung(words, mulai, out, lang="id"):
    """Kata Whisper -> out. Potongan tanpa spasi di depan ('-benar', ',5') disambung ke kata sebelumnya."""
    for w in words or []:
        teks = w.word
        if not teks.strip():
            continue
        if out and teks.lstrip()[0] in "-,.!?%'’)" and (not teks.startswith(" ") or teks.lstrip()[0] in "-,"):
            out[-1]["w"] += teks.strip()
            out[-1]["e"] = round(w.end + mulai, 2)
        else:
            out.append({"t": round(w.start + mulai, 2), "e": round(w.end + mulai, 2), "w": teks.strip(), "l": lang})


# Kata yang hanya muncul di ucapan streamer, tidak pernah di terjemahan paksa dialog NPC.
STREAMER = {"gue", "gua", "gw", "lu", "lo", "guys", "cuy", "cuo", "cua", "anjir", "anjur", "anjay", "njir", "woy",
            "wkwk", "wkwkwk", "bro", "bang", "ges"}


SERU = {"ah", "oh", "eh", "wah", "man", "ok", "oke", "okay", "yeah", "ya", "hah", "hmm", "no", "yes"}


def _inti(w):
    return w.strip().strip(",.!?\"'").lower()


def _npc(seg, kata_en):
    """Apakah kalimat ini dialog NPC berbahasa Inggris yang dipaksa jadi bahasa Indonesia?
    Deteksi bahasa Whisper tidak bisa dipakai (ucapan streamer sering terbaca Jawa/Sunda dengan peluang
    Indonesia 0,01), jadi yang dibandingkan: keyakinan per kata saat dibaca sebagai bahasa Indonesia dan saat
    dibaca sebagai bahasa Inggris. Terjemahan paksa selalu kurang yakin daripada transkrip aslinya."""
    words = seg.words or []
    if not words:
        return False, []
    ids = [_inti(w.word) for w in words]
    if STREAMER & set(ids):
        return False, []
    o = [w for w in kata_en if w.start < seg.end - 0.1 and w.end > seg.start + 0.1]
    if not o:
        return False, []
    pi = sum(w.probability for w in words) / len(words)
    pe = sum(w.probability for w in o) / len(o)
    isi = set(ids) - SERU
    sama = len(isi & {_inti(w.word) for w in o}) / max(1, len(isi))
    if sama >= 0.3:                       # bacaan Inggris tetap memakai kata Indonesia yang sama
        return False, []
    return (pe >= pi + 0.1 and pe >= 0.55) or (pi < 0.55 and pe >= pi), o


def kata_whisper(media, model="small", bahasa="id", mulai=0.0, info_tiap=600, cek_bahasa=False):
    """-> [{"t": detik, "e": akhir, "w": kata, "l": bahasa}] dengan waktu per kata.
    cek_bahasa: klip dibaca sekali lagi sebagai bahasa Inggris; kalimat yang ternyata dialog NPC berbahasa Inggris
    memakai bacaan Inggris itu (l="en"), bukan terjemahan paksa ke bahasa Indonesia. Hanya untuk potongan pendek:
    tiap bacaan large-v3-turbo sekitar 12-20 detik untuk klip 40 detik di CPU."""
    m = _model(model)
    audio = _pcm16k(media) if isinstance(media, str) else media
    opsi = dict(word_timestamps=True, condition_on_previous_text=False, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                beam_size=1 if model in ("tiny", "base", "small", "large-v3-turbo") else 5)
    segs, _ = m.transcribe(audio, language=bahasa, **opsi)
    kata_en = []
    if cek_bahasa:
        segs = list(segs)
        kata_en = [w for x in m.transcribe(audio, language="en", **opsi)[0] for w in (x.words or [])]
    hasil = [(s, *(_npc(s, kata_en) if cek_bahasa else (False, []))) for s in segs]
    # Jawaban pendek NPC ("Sudah.", "Bagus.") di antara dialog Inggris: ikut dialog itu.
    for i, (s, npc, o) in enumerate(hasil):
        kiri = hasil[i - 1][1] if i > 0 else True
        kanan = hasil[i + 1][1] if i + 1 < len(hasil) else True
        ids = {_inti(w.word) for w in s.words or []}
        if cek_bahasa and not npc and len(ids) <= 2 and not STREAMER & ids and kiri and kanan and (i > 0 or i + 1 < len(hasil)):
            hasil[i] = (s, True, [w for w in kata_en if w.start < s.end - 0.1 and w.end > s.start + 0.1])
    out, berikut = [], info_tiap
    for s, npc, o in hasil:
        if npc:
            _gabung(o, mulai, out, "en")
            continue
        _gabung(s.words, mulai, out, bahasa)
        if s.end >= berikut:
            say(f"  transkrip {int(s.end // 60)} menit")
            berikut += info_tiap
    return rapikan(out)


# Salah dengar Whisper yang tetap untuk sapaan gaul streamer.
GAUL = {"cuo": "cuy", "cua": "cuy", "cui": "cuy", "anjur": "anjir"}


def rapikan(kata):
    for k in kata:
        if k.get("l") != "en":
            inti = k["w"].rstrip(",.!?")
            if inti.lower() in GAUL:
                k["w"] = GAUL[inti.lower()] + k["w"][len(inti):]
    return kata


def baris(kata, a, b):
    """Kata-kata dalam [a, b) -> teks."""
    return " ".join(k["w"] for k in kata if a <= k["t"] < b)
