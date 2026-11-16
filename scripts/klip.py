"""klip-gta: stream GTA panjang -> klip vertikal siap posting, untuk clipper Indonesia.

  python scripts/klip.py URL [URL ...] [--klip 3]        satu atau beberapa stream
  python scripts/klip.py --cari --daftar                 lihat stream GTA terbesar sekarang
  python scripts/klip.py --cari --stream 5               cari lalu klip 5 stream
  python scripts/klip.py URL --bagian 2:00:00-4:00:00    hanya sebagian stream (stream 24 jam)
  python scripts/klip.py --cek                           cek alat yang dibutuhkan

Hasil: ~/klip-gta/<tanggal>/<kanal>__<judul>/ berisi klip .mp4, POSTING.md, klip.json, laporan.json.
Mengulang perintah yang sama melanjutkan (langkah yang sudah selesai disimpan di ~/klip-gta/kerja/).
"""
import argparse
import datetime
import json
import os
import platform
import shutil
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from klipgta import unduh  # noqa: E402
from klipgta.pilih import pilih  # noqa: E402
from klipgta.potong import buat_klip  # noqa: E402
from klipgta.sinyal import kenyaringan, skor  # noqa: E402
from klipgta.transkrip import kata_whisper  # noqa: E402
from klipgta.util import HOME, KERJA, hms, load_json, parse_hms, save_json, say, slug  # noqa: E402


def cek():
    ok = True
    for t, cara in (("ffmpeg", "Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg"),
                    ("claude", "pasang Claude Code: https://claude.com/claude-code"),
                    ("node", "Windows: winget install OpenJS.NodeJS.LTS · Mac: brew install node (dipakai yt-dlp untuk YouTube)")):
        p = shutil.which(t)
        print(f"  {'OK ' if p else 'BELUM'}  {t:8s} {p or cara}")
        ok = ok and bool(p)
    try:
        import cv2, faster_whisper, numpy, yt_dlp  # noqa: F401
        print("  OK     paket Python (yt-dlp, faster-whisper, opencv, numpy)")
    except ImportError as e:
        print(f"  BELUM  paket Python: {e}")
        ok = False
    free = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
    print(f"  {'OK ' if free > 5 else 'AWAS'}  disk kosong {free:.0f} GB (butuh sekitar 0,1 GB per jam stream)")
    print(f"  info   {platform.system()} {platform.machine()}, Python {platform.python_version()}")
    print("Semua siap." if ok else "Ada yang belum terpasang (lihat di atas).")
    return ok


def satu_stream(url, a, nomor_stream):
    t_mulai = time.time()
    tahap = {}
    inf = unduh.info(url, a.cookies)
    who = (inf["kanal"] or "?")[:20]
    if inf["live"] == "is_live" and not a.bagian:
        say("stream ini masih live: yang sudah tayang saja yang diproses (pakai --bagian untuk menit berikutnya)", who)
    kerja = os.path.join(KERJA, slug(inf["id"] or inf["judul"], 40))
    os.makedirs(kerja, exist_ok=True)
    bagian = None
    if a.bagian:
        x, y = a.bagian.split("-")
        bagian = (parse_hms(x), parse_hms(y))
    say(f"{inf['judul'][:70]} · {hms(inf['durasi'])}", who)

    # 1. audio + chat bersamaan (chat replay YouTube lambat)
    t = time.time()
    chat_box = {}
    th = None
    if not a.tanpa_chat and inf["chat"]:
        th = threading.Thread(target=lambda: chat_box.update(c=unduh.chat_youtube(url, kerja, a.batas_chat, a.cookies)), daemon=True)
        th.start()
    say("mengunduh audio stream (videonya nanti, hanya menit yang jadi klip) ...", who)
    audio = unduh.audio(url, kerja, a.cookies, bagian)
    tahap["unduh audio"] = round(time.time() - t)

    # 2. transkrip: subtitle otomatis YouTube (cepat) atau Whisper
    t = time.time()
    kata = load_json(os.path.join(kerja, "kata.json"))
    sumber = "cache"
    if kata is None:
        kata = None if a.whisper else unduh.subtitle_youtube(url, kerja, "id", a.cookies)
        sumber = "subtitle otomatis YouTube"
        if not kata:
            say(f"tidak ada subtitle otomatis: transkrip dengan Whisper '{a.model}' (lama untuk stream panjang) ...", who)
            kata = kata_whisper(audio, model=a.model, mulai=bagian[0] if bagian else 0.0)
            sumber = f"Whisper {a.model}"
        save_json(os.path.join(kerja, "kata.json"), kata)
    say(f"transkrip: {len(kata)} kata ({sumber})", who)
    tahap["transkrip"] = round(time.time() - t)

    # 3. kenyaringan + chat -> sinyal
    t = time.time()
    loud = load_json(os.path.join(kerja, "keras.json"))
    if loud is None:
        say("mengukur di mana streamer teriak ...", who)
        loud = kenyaringan(audio)
        if bagian:
            loud = [(x + bagian[0], v) for x, v in loud]
        save_json(os.path.join(kerja, "keras.json"), loud)
    if th:
        say("menunggu chat replay ...", who)
        th.join()
    chat = chat_box.get("c", [])
    dur = inf["durasi"] or (loud[-1][0] if loud else 0)
    sig = skor(dur, chat, loud)
    tahap["dengar"] = round(time.time() - t)

    # 4. Claude memilih
    t = time.time()
    momen = pilih(inf, kata, sig, kerja, jumlah=a.klip, paralel=a.paralel, model=a.model_claude, game=a.game,
                  redo=a.ulang)
    tahap["pilih"] = round(time.time() - t)
    if not momen:
        say("Claude tidak menemukan momen yang layak di stream ini.", who)
        return None

    # 5. klip
    t = time.time()
    tanggal = datetime.date.today().isoformat()
    keluar = os.path.join(HOME, tanggal, f"{slug(inf['kanal'], 24)}__{slug(inf['judul'], 40)}")
    hasil = []
    for i, m in enumerate(momen, 1):
        r = buat_klip(inf, m, i, audio, kerja, keluar, model_teks=a.model_teks, layout_paksa=a.layout,
                      cookies=a.cookies, sensor_kata=not a.tanpa_sensor, kredit=not a.tanpa_kredit, caption=a.caption)
        hasil.append({**m, **r})
    tahap["buat klip"] = round(time.time() - t)
    total = round(time.time() - t_mulai)
    tulis_posting(keluar, inf, hasil, total, tahap)
    save_json(os.path.join(keluar, "klip.json"), hasil)
    save_json(os.path.join(keluar, "laporan.json"), {"stream": inf, "detik_stream": inf["durasi"], "klip": len(hasil),
                                                    "detik_total": total, "tahap_detik": tahap, "transkrip": sumber,
                                                    "pesan_chat": len(chat)})
    say(f"selesai: {len(hasil)} klip dalam {total // 60} menit -> {keluar}", who)
    return keluar


def tulis_posting(keluar, inf, hasil, total, tahap):
    L = [f"# {inf['kanal']}: {inf['judul']}", "", f"Stream: {inf['url']}", "",
         f"{hms(inf['durasi'])} stream -> {len(hasil)} klip dalam {total // 60} menit "
         f"({', '.join(f'{k} {v // 60}:{v % 60:02d}' for k, v in tahap.items())})", "",
         "**Sebelum posting:** tonton tiap klip sampai habis, cek caption dan judulnya, dan pastikan streamer-nya "
         "mengizinkan klip (program clipper resmi atau izin langsung). Tulis kredit streamer di caption.", ""]
    for h in hasil:
        tags = " ".join("#" + x.lstrip("#").replace(" ", "") for x in (h.get("hashtag") or []))
        link = f"{inf['url']}{'&' if '?' in inf['url'] else '?'}t={int(h['mulai_s'])}"
        L += ["---", "", f"## {os.path.basename(h['file'])}", "",
              f"**{h.get('judul', '')}** · {h.get('jenis', '')} · {int(h['selesai_s'] - h['mulai_s'])} dtk · skor {h.get('skor')}", "",
              f"{h.get('caption', '')}", "", f"Kredit: {inf['kanal']} ({link})", "", tags, "",
              f"_Kenapa: {h.get('alasan', '')}_", f"_Dari menit {hms(h['mulai_s'])} · tata letak {h['layout']}_", ""]
    with open(os.path.join(keluar, "POSTING.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="*")
    ap.add_argument("--cek", action="store_true", help="cek alat yang dibutuhkan")
    ap.add_argument("--cari", action="store_true", help="cari stream GTA terbesar sendiri")
    ap.add_argument("--daftar", action="store_true", help="dengan --cari: tampilkan saja, jangan diproses")
    ap.add_argument("--stream", type=int, default=3, help="dengan --cari: berapa stream (default 3)")
    ap.add_argument("--klip", type=int, default=3, help="klip per stream (default 3)")
    ap.add_argument("--bagian", help="hanya bagian ini, mis. 2:00:00-4:00:00")
    ap.add_argument("--cookies", help="ambil login dari browser, mis. chrome / edge / firefox (video dibatasi umur)")
    ap.add_argument("--game", default="GTA", help="nama game untuk judul (default: GTA, ikuti judul stream)")
    ap.add_argument("--model", default="small", help="model Whisper untuk transkrip stream bila tak ada subtitle YouTube")
    ap.add_argument("--model-teks", default="large-v3-turbo",
                    help="model Whisper untuk caption klip (large-v3-turbo = akurat, sekitar 10 detik per klip; small = lebih ringan)")
    ap.add_argument("--model-claude", help="model Claude untuk memilih, mis. sonnet (lebih hemat kuota)")
    ap.add_argument("--paralel", type=int, default=4, help="bagian stream yang dibaca Claude sekaligus")
    ap.add_argument("--layout", default="auto", choices=["auto", "cam", "wajah", "penuh"])
    ap.add_argument("--whisper", action="store_true", help="paksa Whisper walau ada subtitle YouTube")
    ap.add_argument("--tanpa-chat", action="store_true")
    ap.add_argument("--batas-chat", type=int, default=25, help="menit maksimal mengunduh chat replay (default 25)")
    ap.add_argument("--caption", choices=["streamer", "semua"], default="streamer",
                    help="streamer = caption hanya ucapan streamer (default); semua = dialog game bahasa Inggris ikut")
    ap.add_argument("--tanpa-sensor", action="store_true", help="jangan sensor kata kasar di caption")
    ap.add_argument("--tanpa-kredit", action="store_true", help="jangan tulis nama streamer di video")
    ap.add_argument("--ulang", action="store_true", help="minta Claude memilih ulang (audio tetap dipakai)")
    a = ap.parse_args()

    if a.cek:
        sys.exit(0 if cek() else 1)
    urls = list(a.url)
    if a.cari:
        found = unduh.cari_stream(a.stream, cookies=a.cookies)
        for i, s in enumerate(found, 1):
            print(f"  {i}. {s['kanal'][:22]:22s} {s['view']:>10,} view · {'LIVE' if s['live'] else hms(s['durasi'])} · {s['judul'][:60]}")
            print(f"     {s['url']}")
        if a.daftar or not found:
            return
        urls += [s["url"] for s in found]
    if not urls:
        ap.print_help()
        return
    for i, u in enumerate(urls, 1):
        try:
            satu_stream(u, a, i)
        except SystemExit as e:
            say(f"stream dilewati: {e}")


if __name__ == "__main__":
    main()
