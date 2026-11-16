"""Di mana streamer teriak dan chat meledak: skor per 5 detik, dinormalisasi ke sekitarnya (median + MAD dalam
jendela +-5 menit), supaya stream yang makin ramai tidak membuat semua momen jatuh di jam terakhir."""
import bisect
import collections
import re
import statistics
import subprocess

import numpy as np

from .util import say

BIN = 5.0

REAKSI = re.compile(
    r"(KEKW|OMEGALUL|LUL|ICANT|Pog\w*|monka\w*|\bLMA+O+\b|\bHAHA\w*|\bXD+\b|"
    r"\bwk(wk)+\w*|\bxixi\w*|\bakwk\w*|\banjir\w*|\banjay\w*|\bgila\w*|\bngakak\b|\bbjir\w*|\bbuset\b|"
    r"\bwanjir\w*|\bkocak\b|\bhah\b|!{3,}|\?{3,}|:face-with-tears-of-joy:|:rolling-on-the-floor-laughing:|"
    r":skull:|:fire:|:face-screaming-in-fear:|\U0001F602|\U0001F923|\U0001F480|\U0001F525|\U0001F631|\U0001F62D)",
    re.IGNORECASE)
TEKNIS = re.compile(r"(\blag\w*|\bngelag\w*|\bbuffer\w*|\bpatah\w*|\bdelay\b|\bmic\b|\bsuara\w*|\bdc\b|"
                    r"\bcrash\w*|\bfreeze\w*|\bloading\b|\bfps\b|\bping\b|\b360p\b|\b480p\b)", re.IGNORECASE)
_EBU = re.compile(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-inf)")


def kenyaringan(media):
    """Momentary loudness tiap 100 ms (ffmpeg ebur128) -> [(detik, LUFS)]."""
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostats", "-i", media, "-vn", "-af",
                          "aresample=16000,ebur128=framelog=info", "-f", "null", "-"],
                         stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    out = []
    for line in p.stderr:
        m = _EBU.search(line)
        if m:
            v = m.group(2)
            out.append((float(m.group(1)), -120.0 if v == "-inf" else float(v)))
    p.wait()
    return out


def _robust_z(series, half, floor):
    n = len(series)
    out = [0.0] * n
    win = sorted(series[:min(n, half + 1)])
    lo, hi = 0, min(n, half + 1)
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        while hi < b:
            bisect.insort(win, series[hi]); hi += 1
        while lo < a:
            del win[bisect.bisect_left(win, series[lo])]; lo += 1
        med = win[len(win) // 2]
        k = len(win)
        mad = statistics.median(abs(x - med) for x in win) if k < 50 else max(med - win[k // 4], win[(3 * k) // 4] - med)
        out[i] = max(-3.0, min(6.0, (series[i] - med) / max(1.4826 * mad, floor(med), 1e-6)))
    return out


def _smooth(s, r):
    c = np.cumsum([0.0] + list(s))
    n = len(s)
    return [(c[min(n, i + r + 1)] - c[max(0, i - r)]) / (min(n, i + r + 1) - max(0, i - r)) for i in range(n)]


def skor(durasi, chat, loud, chat_lag=6.0):
    """-> dict per bin: skor gabungan, z keras, z chat, jumlah pesan, contoh pesan."""
    n = int(durasi // BIN) + 1
    msgs, reacts, tech = [0.0] * n, [0.0] * n, [0.0] * n
    teks = collections.defaultdict(list)
    for t, m in chat:
        i = int((t - chat_lag) // BIN)
        if 0 <= i < n:
            msgs[i] += 1
            reacts[i] += 1 if REAKSI.search(m) else 0
            tech[i] += 1 if TEKNIS.search(m) else 0
            if len(teks[i]) < 60:
                teks[i].append(m)
    peak = [-120.0] * n
    for t, v in loud:
        i = int(t // BIN)
        if i < n and v > peak[i]:
            peak[i] = v
    half = int(300 // BIN)
    zl = _robust_z(_smooth(peak, 1), half, lambda med: 2.0) if loud else [0.0] * n
    zc = _robust_z(_smooth(msgs, 1), half, lambda med: max(1.0, med) ** 0.5) if chat else [0.0] * n
    zr = _robust_z(_smooth(reacts, 1), half, lambda med: max(1.0, med) ** 0.5) if chat else [0.0] * n
    w = (0.4, 0.3, 0.3) if chat else (0.0, 0.0, 1.0)
    total = []
    for i in range(n):
        s = w[0] * zc[i] + w[1] * zr[i] + w[2] * zl[i]
        if chat and s > 0:
            lo, hi = max(0, i - 3), min(n, i + 4)
            tot = sum(msgs[lo:hi])
            if tot >= 5:
                s *= 1.0 - min(0.7, max(0.0, (sum(tech[lo:hi]) / tot - 0.10) * 2.8))
        total.append(s)
    say(f"sinyal: {len(chat)} pesan chat, {len(loud) // 10} detik audio diukur")
    return {"skor": total, "keras": zl, "chat": zc, "pesan": msgs, "teks": teks}


def tanda(sig, i):
    """Tanda singkat untuk transkrip yang dibaca Claude: [KERAS +3.1] [CHAT x2.4 wkwk|anjir]."""
    out = []
    if sig["keras"][i] >= 2.0:
        out.append(f"[KERAS +{sig['keras'][i]:.1f}]")
    if sig["chat"][i] >= 2.0:
        cnt = collections.Counter(m.strip()[:20] for m in sig["teks"].get(i, []) if m.strip())
        contoh = "|".join(m for m, _ in cnt.most_common(3))
        out.append(f"[CHAT x{sig['chat'][i]:.1f} {contoh}]")
    return " ".join(out)
