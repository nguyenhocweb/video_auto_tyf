import math
import struct
import wave
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("bgm_synthesizer")

SAMPLE_RATE = 44100

def _envelope(t: float, dur: float, attack: float = 0.05, decay: float = 0.1, sustain: float = 0.7, release: float = 0.1) -> float:
    """Tạo đường bao ADSR mượt mà cho nốt nhạc."""
    if t < attack:
        return t / attack if attack > 0 else 1.0
    if t < attack + decay:
        ratio = (t - attack) / decay
        return 1.0 - (1.0 - sustain) * ratio
    if t < dur - release:
        return sustain
    if t < dur:
        ratio = (dur - t) / release
        return max(0.0, sustain * ratio)
    return 0.0

def _osc(freq: float, t: float, kind: str = "sine") -> float:
    """Tạo dao động sóng âm thanh cơ bản."""
    phase = 2.0 * math.pi * freq * t
    if kind == "sine":
        return math.sin(phase) + 0.25 * math.sin(phase * 2) + 0.1 * math.sin(phase * 3)
    if kind == "pluck":
        return (math.sin(phase) + 0.5 * math.sin(phase * 2)) * math.exp(-t * 8.0)
    if kind == "bass":
        return math.sin(phase) + 0.6 * math.sin(phase * 2) + 0.3 * math.sin(phase * 3)
    if kind == "warm_pad":
        return 0.6 * math.sin(phase) + 0.3 * math.sin(phase * 1.005) + 0.2 * math.sin(phase * 2)
    return math.sin(phase)

def _save_wav_and_encode_mp3(samples: list, out_mp3: Path, duration_sec: float) -> bool:
    """Ghi dữ liệu PCM ra file WAV tạm thời rồi nén sang MP3 chất lượng cao bằng FFmpeg."""
    wav_tmp = out_mp3.with_suffix(".tmp.wav")
    try:
        with wave.open(str(wav_tmp), "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            frames = bytearray()
            for left, right in samples:
                # Clamp to 16-bit PCM (-32767 to 32767)
                clamped_l = max(-32767, min(32767, int(left * 30000)))
                clamped_r = max(-32767, min(32767, int(right * 30000)))
                frames.extend(struct.pack("<hh", clamped_l, clamped_r))
            wf.writeframes(frames)

        cmd = [
            "ffmpeg", "-y", "-i", str(wav_tmp),
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(out_mp3)
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0 and out_mp3.exists()
    except Exception as e:
        logger.error(f"Lỗi khi mã hóa MP3 {out_mp3}: {e}")
        return False
    finally:
        if wav_tmp.exists():
            try:
                wav_tmp.unlink()
            except Exception:
                pass

def synthesize_chill(out_path: Path, dur_sec: float = 35.0) -> bool:
    """Tạo nhạc nền Lofi Chill với hợp âm Cmaj7 -> Am7 -> Dm7 -> G7 mượt mà."""
    num_samples = int(SAMPLE_RATE * dur_sec)
    samples = [[0.0, 0.0] for _ in range(num_samples)]
    chords = [
        [261.63, 329.63, 392.00, 493.88], # Cmaj7
        [220.00, 261.63, 329.63, 392.00], # Am7
        [293.66, 349.23, 440.00, 523.25], # Dm7
        [196.00, 246.94, 293.66, 349.23], # G7
    ]
    chord_dur = 4.0
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        chord_idx = int((t % (chord_dur * len(chords))) / chord_dur)
        chord = chords[chord_idx]
        t_in_chord = t % chord_dur
        env = _envelope(t_in_chord, chord_dur, attack=0.3, decay=0.5, sustain=0.6, release=0.4)
        
        sig = sum(_osc(f, t, "warm_pad") for f in chord) * 0.18 * env
        # Nhịp kick nhẹ nhàng
        beat = t % 1.0
        kick = math.sin(2 * math.pi * 55 * beat) * math.exp(-beat * 15) * 0.25 if beat < 0.2 else 0.0
        val = sig + kick
        samples[i][0] = val
        samples[i][1] = val
    return _save_wav_and_encode_mp3(samples, out_path, dur_sec)

def synthesize_upbeat(out_path: Path, dur_sec: float = 30.0) -> bool:
    """Tạo nhạc nền Upbeat Funk nhộn nhịp 120 BPM."""
    num_samples = int(SAMPLE_RATE * dur_sec)
    samples = [[0.0, 0.0] for _ in range(num_samples)]
    bass_notes = [146.83, 146.83, 174.61, 196.00, 220.00, 196.00, 174.61, 130.81] # D minor bass
    beat_dur = 0.5 # 120 BPM
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        step = int((t % (beat_dur * len(bass_notes))) / beat_dur)
        note_freq = bass_notes[step]
        t_in_step = t % beat_dur
        env = _envelope(t_in_step, beat_dur, attack=0.01, decay=0.1, sustain=0.4, release=0.1)
        bass = _osc(note_freq, t, "bass") * 0.35 * env
        
        # Nhịp beat
        beat_t = t % 0.5
        clap = (math.sin(t * 1200) * 0.15) if (0.24 < (t % 1.0) < 0.28 or 0.74 < (t % 1.0) < 0.78) else 0.0
        val = bass + clap
        samples[i][0] = val
        samples[i][1] = val
    return _save_wav_and_encode_mp3(samples, out_path, dur_sec)

def synthesize_funny(out_path: Path, dur_sec: float = 25.0) -> bool:
    """Tạo nhạc nền Funny/Comedy phong cách hoạt hình nốt gảy pizzicato."""
    num_samples = int(SAMPLE_RATE * dur_sec)
    samples = [[0.0, 0.0] for _ in range(num_samples)]
    melody = [392.00, 440.00, 493.88, 587.33, 523.25, 440.00, 392.00, 329.63]
    step_dur = 0.35
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        step = int((t % (step_dur * len(melody))) / step_dur)
        freq = melody[step]
        t_note = t % step_dur
        pizz = _osc(freq, t_note, "pluck") * 0.4
        samples[i][0] = pizz
        samples[i][1] = pizz
    return _save_wav_and_encode_mp3(samples, out_path, dur_sec)

def synthesize_asmr(out_path: Path, dur_sec: float = 35.0) -> bool:
    """Tạo nhạc nền ASMR thư giãn, êm dịu, không lời."""
    num_samples = int(SAMPLE_RATE * dur_sec)
    samples = [[0.0, 0.0] for _ in range(num_samples)]
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        # Dải hòa âm 432Hz & F major êm dịu
        drone = (math.sin(2 * math.pi * 174.61 * t) * 0.2 +
                 math.sin(2 * math.pi * 220.00 * t) * 0.15 +
                 math.sin(2 * math.pi * 261.63 * t * 1.002) * 0.15)
        # Sóng chậm thư giãn
        lfo = 0.5 + 0.5 * math.sin(2 * math.pi * 0.1 * t)
        val = drone * lfo * 0.7
        samples[i][0] = val
        samples[i][1] = val
    return _save_wav_and_encode_mp3(samples, out_path, dur_sec)

def synthesize_cinematic(out_path: Path, dur_sec: float = 35.0) -> bool:
    """Tạo nhạc nền Cinematic kịch tính với âm trầm mạnh mẽ."""
    num_samples = int(SAMPLE_RATE * dur_sec)
    samples = [[0.0, 0.0] for _ in range(num_samples)]
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        # D drone trầm
        sub = math.sin(2 * math.pi * 73.42 * t) * 0.35
        # Nhịp đập tim/suspense
        pulse_t = t % 1.2
        pulse = math.sin(2 * math.pi * 50 * pulse_t) * math.exp(-pulse_t * 6) * 0.3 if pulse_t < 0.4 else 0.0
        # Tension swell
        swell = math.sin(2 * math.pi * 146.83 * t) * (0.1 + 0.1 * math.sin(2 * math.pi * 0.25 * t))
        val = sub + pulse + swell
        samples[i][0] = val
        samples[i][1] = val
    return _save_wav_and_encode_mp3(samples, out_path, dur_sec)

def ensure_preset_audio_files(storage_dir: Path) -> dict:
    """Đảm bảo các file audio mẫu có sẵn trên máy chủ để phát trực tuyến và hòa âm."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    presets = {
        "preset_chill.mp3": synthesize_chill,
        "preset_upbeat.mp3": synthesize_upbeat,
        "preset_funny.mp3": synthesize_funny,
        "preset_asmr.mp3": synthesize_asmr,
        "preset_cinematic.mp3": synthesize_cinematic,
    }
    results = {}
    for filename, synth_fn in presets.items():
        file_path = storage_dir / filename
        if not file_path.exists() or file_path.stat().st_size < 1024:
            logger.info(f"Đang tự động khởi tạo file nhạc mẫu {filename}...")
            ok = synth_fn(file_path)
            results[filename] = ok
        else:
            results[filename] = True
    return results

