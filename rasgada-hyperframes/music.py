"""Trilha sintetizada (estilo menu de game de surf dos anos 2000) + efeitos sincronizados.
Gera assets/audio/trilha.mp3 com 42 s (só a música). Uso: python3 music.py
Os tempos dos efeitos seguem a linha do tempo de src/main.js (SCENES).
"""
import numpy as np
from scipy.signal import butter, lfilter
import wave, os

SR = 44100
DUR = 42.0
N = int(SR * DUR)
BPM = 120
BEAT = 60 / BPM
rng = np.random.default_rng(5)

mix = np.zeros((N, 2))


def t_arr(n):
    return np.arange(n) / SR


def add(sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    l = gain * np.sqrt(0.5 * (1 - pan))
    r = gain * np.sqrt(0.5 * (1 + pan))
    mix[i:i + len(sig), 0] += sig * l
    mix[i:i + len(sig), 1] += sig * r


def lp(x, fc, order=2):
    b, a = butter(order, min(fc, SR * 0.45) / (SR / 2), 'low')
    return lfilter(b, a, x)


def hp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), 'high')
    return lfilter(b, a, x)


def env(n, a=0.005, d=0.2, s=0.0, rel=0.05, hold=None):
    t = t_arr(n)
    e = np.minimum(t / max(a, 1e-4), 1.0)
    if hold is None:
        e = e * np.exp(-np.maximum(t - a, 0) / d) * (1 - s) + s * (t > a)
    else:
        e = e * np.where(t < hold, 1.0, np.exp(-(t - hold) / rel))
    return e


def note_hz(n):  # n: semitons a partir do A4
    return 440.0 * 2 ** (n / 12)


# ------------------------------------------------------------- instrumentos
def kick():
    n = int(0.35 * SR); t = t_arr(n)
    f = 45 + 110 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 9) * 1.0 + 0.3 * np.tanh(4 * np.sin(ph)) * np.exp(-t * 30)


def snare():
    n = int(0.25 * SR); t = t_arr(n)
    noise = hp(rng.standard_normal(n), 1500) * np.exp(-t * 18)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25)
    return 0.55 * noise + 0.5 * tone


def hat(open_=False):
    n = int((0.18 if open_ else 0.05) * SR); t = t_arr(n)
    return hp(rng.standard_normal(n), 7000) * np.exp(-t * (14 if open_ else 70)) * 0.5


def saw(f, n):
    t = t_arr(n); ph = (f * t) % 1.0
    return 2 * ph - 1


def square(f, n, duty=0.5):
    t = t_arr(n); return np.where((f * t) % 1.0 < duty, 1.0, -1.0)


def bass(f, dur):
    n = int(dur * SR)
    x = saw(f, n) * 0.6 + square(f / 2, n) * 0.4
    x = lp(x, 900) * env(n, 0.004, 0.25, 0.35)
    return np.tanh(x * 1.6) * 0.6


def pluck(f, dur):
    n = int(dur * SR)
    x = square(f, n, 0.25) * 0.5 + square(f * 1.005, n, 0.5) * 0.3
    return lp(x, 3500) * env(n, 0.002, 0.12)


def pad(freqs, dur):
    n = int(dur * SR); x = np.zeros(n)
    for f in freqs:
        for det in (-0.006, 0.0, 0.007):
            x += saw(f * (1 + det), n)
    x = lp(x / (len(freqs) * 3), 1400)
    t = t_arr(n)
    e = np.minimum(t / 0.25, 1) * np.minimum((dur - t) / 0.3, 1)
    return x * np.clip(e, 0, 1)


# A maior: A - E - F#m - D  (semitons relativos ao A4)
CHORDS = [(0, [0, 4, 7]), (-5, [-5, -1, 2]), (-3, [-3, 0, 4]), (-7, [-7, -3, 0])]


def section_level(t):
    """Intensidade da música por momento do vídeo."""
    if t < 3.5: return 'intro'
    if t < 18.5: return 'full'
    if t < 23.0: return 'slow'
    if t < 23.72: return 'build'
    if t < 35.5: return 'full2'
    return 'outro'


music = np.zeros((N, 2))


def madd(sig, at, gain, pan=0.0):
    i = int(at * SR)
    if i >= N or i < 0: return
    sig = sig[: N - i]
    music[i:i + len(sig), 0] += sig * gain * np.sqrt(0.5 * (1 - pan))
    music[i:i + len(sig), 1] += sig * gain * np.sqrt(0.5 * (1 + pan))


K, S = kick(), snare()
H, HO = hat(), hat(True)
step = BEAT / 4  # semicolcheia
nsteps = int(DUR / step)
for k in range(nsteps):
    t = k * step
    sec = section_level(t)
    bar = int(t / (4 * BEAT)); pos = k % 16
    root, tri = CHORDS[bar % 4]
    if sec == 'intro':
        if t > 0.25 and pos in (0, 8): madd(K, t, 0.9)
        if pos % 2 == 0: madd(H, t, 0.25 * (t / 3.5), 0.3)
        continue
    if sec == 'slow':
        # meio tempo, abafado
        if pos == 0: madd(K, t, 0.7)
        if pos == 8 and t < 20.5: madd(S, t, 0.35)
        continue
    full = sec in ('full', 'full2', 'outro')
    if full or sec == 'build':
        if pos in (0, 6, 10) or (sec != 'build' and pos == 8 and bar % 2): madd(K, t, 0.95)
        if pos in (4, 12): madd(S, t, 0.7)
        if sec == 'build' and pos % 2 == 0: madd(S, t, 0.25 + 0.5 * (t - 23.0) / 0.72)
        if pos % 2 == 0: madd(H, t, 0.32, 0.35)
        if pos == 14: madd(HO, t, 0.25, 0.35)
    if full:
        # baixo em colcheias
        if pos % 2 == 0:
            f = note_hz(root - 24 + (12 if pos in (6, 14) else 0))
            madd(bass(f, step * 1.8), t, 0.55)
        # arpejo
        arp = [tri[0], tri[1], tri[2], tri[1] + 12, tri[2] + 12, tri[1] + 12, tri[2], tri[1]]
        if sec != 'full' or t > 8.5:
            madd(pluck(note_hz(arp[pos % 8] + 12), step * 0.9), t, 0.13, -0.4 if pos % 2 else 0.4)
    if pos == 0 and sec in ('full', 'full2', 'outro', 'slow'):
        madd(pad([note_hz(n) for n in tri], 4 * BEAT), t, 0.22)

# pad nas partes lentas
for b in range(int(18.5 / (4 * BEAT)), int(25.5 / (4 * BEAT)) + 1):
    t = b * 4 * BEAT
    if 18.0 <= t < 22.9:
        root, tri = CHORDS[b % 4]
        madd(pad([note_hz(n - 12) for n in tri] + [note_hz(root - 24)], 4 * BEAT), t, 0.35)

# filtro abafado durante a câmera lenta
i0, i1 = int(18.5 * SR), int(23.0 * SR)
for ch in range(2):
    seg = music[i0:i1, ch].copy()
    music[i0:i1, ch] = lp(seg, 650, 2)
# fade final
fo = int(2.5 * SR)
music[-fo:] *= np.linspace(1, 0, fo)[:, None]
mix += music * 0.8


# ------------------------------------------------------------- efeitos
def whoosh(dur=0.45, up=True):
    n = int(dur * SR); t = t_arr(n)
    x = rng.standard_normal(n)
    out = np.zeros(n); blocks = 24
    for bi in range(blocks):
        a, b = bi * n // blocks, (bi + 1) * n // blocks
        frac = bi / blocks
        fc = 400 + 5000 * (frac if up else 1 - frac)
        out[a:b] = lp(x[a:b], fc)
    return out * np.sin(np.pi * t / dur) ** 2 * 0.7


def blip(f0=880, f1=1320, dur=0.12):
    n = int(dur * SR); t = t_arr(n)
    f = np.where(t < dur / 2, f0, f1)
    return square(1, n) * 0 + np.where(((np.cumsum(f) / SR) % 1) < 0.5, 1, -1) * env(n, 0.002, dur / 2) * 0.35


def splash(dur=1.2, bright=1.0):
    n = int(dur * SR); t = t_arr(n)
    x = rng.standard_normal(n)
    x = hp(x, 300) * 0.6 + lp(x, 2500 * bright) * 0.6
    return x * np.exp(-t * 3.2) * np.minimum(t / 0.01, 1)


def boom():
    n = int(1.2 * SR); t = t_arr(n)
    f = 38 + 90 * np.exp(-t * 6)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.5) + 0.25 * lp(rng.standard_normal(n), 800) * np.exp(-t * 6)


def jingle(base=12, dur_note=0.07):
    notes = [0, 4, 7, 12, 16, 19, 24]
    out = np.zeros(int(SR * (dur_note * len(notes) + 0.5)))
    for i, nn in enumerate(notes):
        p = pluck(note_hz(base + nn), 0.35)
        a = int(i * dur_note * SR); out[a:a + len(p)] += p
    return out


# Efeitos: na versão HyperFrames eles são clipes <audio> separados (index.html).

# master
peak = np.max(np.abs(mix))
mix = np.tanh(mix / peak * 1.2) * 0.8
os.makedirs('assets/audio', exist_ok=True)
pcm = (mix * 32767).astype('<i2')
with wave.open('assets/audio/trilha.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())
import subprocess
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', 'assets/audio/trilha.wav', '-c:a', 'libmp3lame', '-b:a', '192k', 'assets/audio/trilha.mp3'], check=True)
os.remove('assets/audio/trilha.wav')
print('assets/audio/trilha.mp3', DUR, 's')
