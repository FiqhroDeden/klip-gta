# klip-gta: skill Claude Code gratis untuk clipper GTA Indonesia

Kasih link stream GTA (atau biarkan dia mencari stream terbesar sendiri), dan kamu dapat klip vertikal siap posting:
momen paling heboh, facecam di atas, gameplay di bawah, judul hook dan caption per kata **berbahasa Indonesia**.
Tiap klip juga dapat judul, caption, hashtag dan kredit untuk ditempel.

- **Mendengarkan seluruh stream untukmu.** Transkrip bahasa Indonesia, tanda di mana streamer teriak dan chat
  meledak, lalu Claude memilih momen yang layak.
- **Caption bahasa Indonesia yang benar.** Ditranskrip ulang per klip dengan Whisper `large-v3-turbo`, kata yang
  sedang diucapkan menyala, kata kasar disensor. Dialog NPC berbahasa Inggris tidak diterjemahkan paksa.
- **Rp0 per klip.** Semua jalan di komputermu sendiri; Claude pakai langganan Claude Code-mu. Tanpa API key.
- **Unduhan kecil.** Hanya audio stream dan menit-menit yang jadi klip.
- **Windows dan Mac.**

## Pasang
1. Pasang alatnya (sekali saja):
   - Windows: `winget install astral-sh.uv Gyan.FFmpeg OpenJS.NodeJS.LTS`
   - Mac: `brew install uv ffmpeg node`
2. Salin folder ini ke folder skill Claude Code: `~/.claude/skills/klip-gta`
   (di Windows: `C:\Users\<nama>\.claude\skills\klip-gta`), atau:
   ```bash
   git clone https://github.com/FiqhroDeden/klip-gta ~/.claude/skills/klip-gta
   ```
3. Buka Claude Code dan ketik:
   > Jalankan `bash ~/.claude/skills/klip-gta/scripts/klip-gta --cek` sampai "Semua siap", lalu
   > `--cari --daftar` dan ceritakan apa yang ditemukan.

Setelah itu cukup bilang: *"klipin stream ini: <link>"* atau *"cari stream GTA terbesar hari ini dan klipin"*.

## Perlu diingat
- **Minta izin dulu.** Klip hanya streamer yang mengizinkan (program clipper resmi atau izin langsung). Klip tanpa
  izin bisa kena klaim hak cipta.
- **Tambahkan suaramu sendiri.** Klip yang cuma diunggah ulang jangkauannya kecil; voice-over singkat 2-5 detik di
  awal, judul hook dan caption Indonesia membuat klipmu berbeda.
- **Tonton sebelum posting.** Mesin bisa salah dengar; cek caption dan judulnya.
- Video dibatasi umur di YouTube: tambahkan `--cookies chrome`.

Isi: `SKILL.md` (yang diikuti Claude) · `scripts/klip-gta` dan `klip-gta.cmd` (perintahnya) · `scripts/klipgta/`
(unduh, sinyal, transkrip, pilih, potong) · `streamer.txt` (daftar pantau bawaan) · `assets/fonts` (Anton, Inter: SIL OFL).

Lisensi MIT. Font: SIL Open Font License 1.1 (lihat `assets/fonts`).
