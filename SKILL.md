---
name: klip-gta
description: Clipper GTA untuk kreator Indonesia. Mengubah stream GTA yang panjang (YouTube, dan Twitch/Kick lewat link) jadi klip vertikal 9:16 siap posting di TikTok, Reels dan Shorts - facecam di atas, gameplay di bawah, judul hook dan caption per kata berbahasa Indonesia - plus POSTING.md berisi judul, caption, hashtag dan kredit per klip. Mendengarkan seluruh stream di komputer sendiri, menandai bagian streamer teriak dan chat meledak, lalu Claude memilih momen yang paling layak. Memakai langganan Claude sendiri, tanpa API key dan tanpa kredit. Pakai setiap kali pengguna ingin mengklip stream GTA (GTA 6, GTA 5, GTA RP) atau stream game lain, mencari momen terbaik dari VOD, membuat klip dari stream Windah, MiawAug atau streamer mana pun, atau berkata "klipin stream ini", "cari momen lucunya", "bikin klip dari live ini".
---

# klip-gta

Stream masuk, klip siap posting keluar. **Kamu yang menjalankan; pengguna cukup memberi link** (atau tidak sama
sekali: `--cari`). `SKILL` = folder tempat file ini berada. Perintahnya:

```bash
bash SKILL/scripts/klip-gta URL            # Mac, Linux, Git Bash di Windows
SKILL\scripts\klip-gta.cmd URL             # Command Prompt / PowerShell di Windows
```

Hasil ada di `~/klip-gta/<tanggal>/<kanal>__<judul>/`: klip `.mp4`, `POSTING.md`, `klip.json`, `laporan.json`.

## 0. Pertama kali di sebuah komputer
1. Butuh: `uv` (pengelola Python), `ffmpeg`, `node` (dipakai yt-dlp untuk YouTube) dan Claude Code.
   - Windows: `winget install astral-sh.uv Gyan.FFmpeg OpenJS.NodeJS.LTS`
   - Mac: `brew install uv ffmpeg node`
   Pasang dengan cara resmi itu; tanya pengguna dulu sebelum memasang apa pun yang meminta password.
2. `bash SKILL/scripts/klip-gta --cek` sampai tertulis **Semua siap.** Pertama kali, `uv` memasang paket Python
   skill ini sendiri (sekitar 300 MB), dan Whisper mengunduh modelnya saat pertama dipakai (`small` sekitar 480 MB untuk transkrip stream bila tak ada
   subtitle YouTube, `large-v3-turbo` sekitar 1,6 GB untuk caption).

## 1. Apa yang terjadi pada tiap stream
1. **Audio saja** yang diunduh (stream 4 jam sekitar 250 MB). Videonya tidak.
2. **Transkrip bahasa Indonesia**: subtitle otomatis YouTube kalau ada (cepat, gratis), kalau tidak Whisper `small`
   di komputer sendiri (lama untuk stream panjang; bisa diganti `--model base` yang lebih cepat tapi kurang tepat).
3. **Sinyal**: kenyaringan per 100 ms (teriak, kaget) dan, untuk VOD YouTube bekas live, chat replay (pesan per
   5 detik dan reaksi seperti wkwk/anjir/KEKW). Keduanya dinilai terhadap sekitarnya, bukan rata-rata seluruh stream.
4. **Pilih**: Claude (`claude -p`, langganan pengguna) membaca transkrip per 10 menit dengan tanda `[KERAS]` dan
   `[CHAT]`, 4 bagian sekaligus, lalu memilih momen 15-45 detik dengan judul hook, caption, hashtag dan skor 1-100.
   Yang terbaik dan tidak berdekatan diambil (`--klip N` per stream).
5. **Klip**: hanya menit itu yang diunduh videonya, diselaraskan dengan audio stream (korelasi silang, karena yt-dlp
   memotong di keyframe), facecam dicari otomatis:
   - facecam kecil → **facecam di atas, gameplay di bawah**, judul di sambungannya;
   - wajah besar (stream kamera) → potong 9:16 mengikuti wajah;
   - tanpa wajah → gambar utuh di atas latar blur.
   Caption ditranskrip ulang dari potongan itu dengan Whisper `large-v3-turbo` (sekitar 10 detik per klip di CPU,
   hasilnya sama tiap dijalankan), kata yang diucapkan menyala kuning. Tiap kalimat dicek bahasanya: dialog NPC
   berbahasa Inggris tidak dipaksa jadi bahasa Indonesia, dan secara bawaan tidak ikut jadi caption (`--caption semua`
   menampilkannya dalam bahasa Inggris). Kata kasar disensor (`a****`). Kredit kanal di pojok. Loudness -14 LUFS.
6. **POSTING.md**: judul, caption, hashtag, link ke menit aslinya, kredit, dan alasan Claude memilihnya.

## 2. Menjalankan
Jalankan proses panjang di background dan ceritakan ke pengguna apa yang sedang terjadi dengan bahasa biasa.
```bash
bash SKILL/scripts/klip-gta URL                         # satu stream, 3 klip
bash SKILL/scripts/klip-gta URL URL --klip 4            # beberapa stream, 4 klip per stream
bash SKILL/scripts/klip-gta --cari --daftar             # tampilkan stream GTA terbesar sekarang
bash SKILL/scripts/klip-gta --cari --stream 5           # cari lalu klip 5 stream
bash SKILL/scripts/klip-gta URL --bagian 2:00:00-4:00:00   # hanya sebagian (stream 24 jam)
```
| opsi | gunanya |
|---|---|
| `--klip N` | klip per stream (default 3) |
| `--bagian A-B` | hanya rentang `h:mm:ss-h:mm:ss`; untuk stream yang masih live, proses jam-jam barunya saja |
| `--cookies chrome` | pakai login browser (video dibatasi umur, VOD khusus subscriber) |
| `--model base` / `--model-teks small` | Whisper lebih cepat untuk transkrip stream / caption (komputer lemah; caption kurang tepat) |
| `--caption semua` | dialog NPC game (bahasa Inggris) ikut jadi caption; bawaannya hanya ucapan streamer |
| `--model-claude sonnet` | model Claude yang lebih hemat kuota untuk memilih |
| `--layout cam/wajah/penuh` | paksa tata letak (default `auto` per klip) |
| `--tanpa-chat` | lewati chat replay (lebih cepat) · `--batas-chat 25` menit maksimal mengunduh chat |
| `--tanpa-sensor`, `--tanpa-kredit` | caption tanpa sensor / tanpa nama kanal di video |
| `--ulang` | minta Claude memilih ulang (audio dan transkrip tetap dipakai) |

Mengulang perintah yang sama melanjutkan dari langkah terakhir (`~/klip-gta/kerja/`).

## 3. Mencari stream (`--cari`)
Pencarian YouTube "GTA 6 live indonesia" dan sejenisnya, ditambah daftar pantau `~/klip-gta/streamer.txt`
(kanal YouTube, satu per baris; dibuat dari bawaan skill saat pertama dipakai). Ubah daftar itu bersama pengguna:
masukkan streamer yang **mengizinkan** klip. Twitch dan Kick: tempel link VOD-nya langsung.

## 4. Sebelum pengguna posting
Buka tiap klip (atau beberapa frame-nya) dan cek: facecam berisi wajah, caption terbaca dan benar, judul menyebut
streamer yang benar, tidak ada spoiler cerita besar tanpa peringatan. **Pengguna yang memposting; jangan pernah
memposting untuk mereka.** Ingatkan dua hal:
- **Izin.** Klip hanya streamer yang mengizinkan (program clipper resmi atau izin langsung). Tanpa izin, klip bisa
  kena klaim hak cipta.
- **Konten daur ulang.** TikTok dan YouTube menurunkan jangkauan klip yang cuma diunggah ulang. Yang menambah nilai:
  judul hook sendiri, caption Indonesia, dan terutama voice-over singkat 2-5 detik di awal dari pengguna sendiri.

## 5. Masalah umum
- **"Sign in to confirm your age"** → `--cookies chrome` (browser tempat pengguna login YouTube).
- **"penyelarasan lemah"** di sebuah klip → waktunya bisa meleset sekitar 1 detik; cek klip itu.
- **Transkrip lama** → stream tanpa subtitle otomatis ditranskrip Whisper di komputer sendiri; pakai `--bagian`
  atau `--model base`.
- **Chat lambat** → chat replay YouTube diunduh halaman demi halaman (3,5 jam stream bisa 30+ menit); dibatasi
  `--batas-chat` menit, yang sudah terunduh tetap dipakai. `--tanpa-chat` untuk melewatinya.
- **Claude tidak menemukan apa-apa** → stream yang sepi; coba stream lain atau `--klip` lebih kecil.
