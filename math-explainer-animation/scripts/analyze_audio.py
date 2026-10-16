#!/usr/bin/env python3
"""Read real audio and save cautious editing cues, never confirmed downbeats.

Example: python analyze_audio.py music.wav --out qa/music.json --video-fps 30
Requires numpy; non-PCM-WAV files also require FFmpeg on PATH, --ffmpeg, or
FFMPEG_BINARY. This is a lightweight onset/tempo estimator, not beat annotation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave


def executable(explicit: str | None, env: str, name: str) -> str:
    value = explicit or os.environ.get(env) or shutil.which(name)
    if not value:
        raise RuntimeError(f"{name} not found. Use --{name}, {env}, or PATH.")
    found = shutil.which(value)
    if found:
        return found
    if Path(value).is_file():
        return str(Path(value).resolve())
    raise RuntimeError(f"{name} executable does not exist: {value}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_audio(path: Path, ffmpeg: str | None, max_seconds: float):
    import numpy as np
    # PCM WAV can be read without an external decoder. Float/compressed WAV is
    # deliberately delegated to FFmpeg rather than interpreted as integer PCM.
    try:
        with wave.open(str(path), "rb") as source:
            channels, rate, width, count = source.getnchannels(), source.getframerate(), source.getsampwidth(), source.getnframes()
            if count / rate > max_seconds:
                raise ValueError(f"Audio exceeds --max-seconds ({max_seconds:g}); analyze a chosen excerpt first.")
            if source.getcomptype() != "NONE" or width not in (1, 2, 3, 4):
                raise wave.Error("Unsupported PCM format")
            raw = source.readframes(count)
        if width == 1:
            samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128) / 128
        elif width in (2, 4):
            samples = np.frombuffer(raw, dtype="<i2" if width == 2 else "<i4").astype(np.float64) / (2 ** (8 * width - 1))
        else:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            values = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            values = (values ^ 0x800000) - 0x800000
            samples = values.astype(np.float64) / 8388608
        return samples.reshape(-1, channels).mean(axis=1), rate, channels, "Python wave / integer PCM"
    except (wave.Error, EOFError):
        binary = executable(ffmpeg, "FFMPEG_BINARY", "ffmpeg")
        rate = 22050
        command = [binary, "-v", "error", "-i", str(path), "-map", "0:a:0", "-t", str(max_seconds + 1), "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
        decoded = subprocess.run(command, capture_output=True, check=False)
        if decoded.returncode:
            raise RuntimeError("Audio decoding failed: " + decoded.stderr.decode("utf8", errors="replace")[-2000:])
        samples = np.frombuffer(decoded.stdout, dtype="<f4").astype(np.float64)
        if len(samples) / rate > max_seconds:
            raise ValueError(f"Audio exceeds --max-seconds ({max_seconds:g}); analyze a chosen excerpt first.")
        return samples, rate, None, "FFmpeg first audio stream, mono analysis decode"


def analyze(samples, rate: int, video_fps: float, min_bpm: float, max_bpm: float):
    import numpy as np
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError("Audio is empty or contains non-finite samples.")
    # Downsample only for analysis, retaining a separate analysis time base.
    stride = max(1, int(rate / 22050))
    signal = samples[::stride]
    analysis_rate = rate / stride
    window = 1024
    hop = max(1, round(analysis_rate * 0.01))
    if len(signal) < window:
        return {"analysisSampleRate": analysis_rate, "analysisHopSamples": hop,
                "analysisHopSeconds": hop / analysis_rate, "onsetCandidates": [],
                "estimatedBpm": None, "bpmReliability": 0, "unreliableReason": "Audio is shorter than one analysis window.",
                "beatCandidates": [], "sectionChangeCandidates": []}
    framed = np.lib.stride_tricks.sliding_window_view(signal, window)[::hop]
    rms = np.zeros(len(framed))
    # Chunk FFT work to avoid a full recording-sized complex spectrogram.
    flux = np.zeros(len(framed))
    previous = None
    taper = np.hanning(window)
    for start in range(0, len(framed), 2048):
        block = framed[start:start + 2048]
        rms[start:start + len(block)] = np.sqrt(np.mean(block ** 2, axis=1))
        magnitude = np.log1p(np.abs(np.fft.rfft(block * taper, axis=1)))
        prior = np.vstack([previous if previous is not None else magnitude[0], magnitude[:-1]])
        flux[start:start + len(magnitude)] = np.maximum(magnitude - prior, 0).sum(axis=1)
        previous = magnitude[-1]
    energy_rise = np.maximum(np.diff(rms, prepend=rms[0]), 0)
    if flux.max() > 0:
        flux /= flux.max()
    if energy_rise.max() > 0:
        energy_rise /= energy_rise.max()
    novelty = 0.75 * flux + 0.25 * energy_rise
    threshold = max(float(np.percentile(novelty, 75) + 0.3 * np.std(novelty)), 0.035)
    peaks = np.flatnonzero((novelty[1:-1] > novelty[:-2]) & (novelty[1:-1] >= novelty[2:]) & (novelty[1:-1] >= threshold)) + 1
    # Greedy non-maximum suppression makes nearby FFT frames one candidate.
    kept = []
    separation = max(1, round(0.12 * analysis_rate / hop))
    for index in sorted(peaks.tolist(), key=lambda p: float(novelty[p]), reverse=True):
        if all(abs(index - chosen) >= separation for chosen in kept):
            kept.append(index)
    kept.sort()

    def cue(seconds: float, **extra):
        # A video frame is derived from seconds, never an FFT or hop index.
        seconds = round(float(seconds), 6)
        return {"seconds": seconds, "videoFrame": int(math.floor(seconds * video_fps + 0.5)), **extra}

    onsets = [cue(index * hop / analysis_rate + window / (2 * analysis_rate), strength=round(float(novelty[index]), 4), estimated=True) for index in kept]
    envelope = novelty - novelty.mean()
    minimum_lag = max(1, math.ceil(60 / max_bpm * analysis_rate / hop))
    maximum_lag = min(len(envelope) // 2, math.floor(60 / min_bpm * analysis_rate / hop))
    scores = []
    for lag in range(minimum_lag, maximum_lag + 1):
        a, b = envelope[:-lag], envelope[lag:]
        denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
        scores.append((float(np.dot(a, b) / denominator) if denominator > 1e-12 else 0, lag))
    score, lag = max(scores, default=(0, 0))
    duration = len(samples) / rate
    reason = None
    if duration < 6:
        reason = "Less than 6 seconds: too little context for a reliable tempo estimate."
    elif len(kept) < 5:
        reason = "Fewer than 5 salient onset candidates."
    elif score < 0.18 or not lag:
        reason = "No sufficiently stable periodic onset pattern was detected."
    elif float(rms.max()) < 0.0001:
        reason = "Signal is effectively silent."
    bpm = 60 * analysis_rate / hop / lag if lag and reason is None else None
    beats = []
    if bpm:
        # Pick a plausible grid phase by onset-energy support. It is still only
        # an estimate, including possible half/double-tempo ambiguity.
        phase = max(range(lag), key=lambda offset: float(novelty[offset::lag].sum()))
        beats = [cue(i * hop / analysis_rate + window / (2 * analysis_rate), estimated=True, confirmedDownbeat=False) for i in range(phase, len(novelty), lag)]
    # Coarse level changes are editorial prompts, not named musical sections.
    block_frames = max(1, round(1.0 * analysis_rate / hop))
    levels = [float(np.sqrt(np.mean(rms[i:i + block_frames] ** 2))) for i in range(0, len(rms), block_frames)]
    changes = []
    for i in range(1, len(levels)):
        delta = 20 * math.log10(max(levels[i], 1e-8) / max(levels[i - 1], 1e-8))
        if abs(delta) >= 6:
            changes.append(cue(i * block_frames * hop / analysis_rate, levelChangeDb=round(delta, 2), estimated=True))
    return {"analysisSampleRate": analysis_rate, "analysisWindowSamples": window, "analysisHopSamples": hop,
            "analysisHopSeconds": hop / analysis_rate, "onsetCandidates": onsets,
            "estimatedBpm": round(bpm, 3) if bpm else None, "bpmReliability": round(max(0, score), 4),
            "reliabilityMeaning": "Normalized onset autocorrelation, not a calibrated probability.",
            "unreliableReason": reason, "beatCandidates": beats, "sectionChangeCandidates": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", type=Path, help="User-selected audio file; no download or upload is performed")
    parser.add_argument("--out", type=Path, default=Path("audio-analysis.json"))
    parser.add_argument("--video-fps", type=float, default=30)
    parser.add_argument("--ffmpeg", help="Decoder path; alternatively FFMPEG_BINARY or PATH")
    parser.add_argument("--min-bpm", type=float, default=50)
    parser.add_argument("--max-bpm", type=float, default=200)
    parser.add_argument("--max-seconds", type=float, default=1800, help="Memory guard; default 30 minutes")
    args = parser.parse_args()
    if args.video_fps <= 0 or args.max_seconds <= 0 or not 0 < args.min_bpm < args.max_bpm:
        parser.error("fps/max-seconds must be positive; require 0 < min-bpm < max-bpm")
    report = {"analysisComplete": False, "file": str(args.audio.resolve()), "confirmedDownbeats": [],
              "manualListeningComplete": False, "rightsConfirmed": False,
              "caution": "Onsets, tempo, beat grid and level changes are estimates. Listen and annotate downbeats/sections before editing; half/double tempo is possible.",
              "videoFps": args.video_fps, "videoFrameFormula": "floor(seconds * videoFps + 0.5), not analysis-frame index"}
    try:
        if not args.audio.is_file():
            raise FileNotFoundError(f"Audio does not exist: {args.audio}")
        samples, rate, channels, decoder = read_audio(args.audio, args.ffmpeg, args.max_seconds)
        report.update(sha256=sha256(args.audio), durationSeconds=len(samples) / rate,
                      decodedSampleRate=rate, originalChannelsIfPcmWav=channels, decoder=decoder)
        report.update(analyze(samples, rate, args.video_fps, args.min_bpm, args.max_bpm))
        report["analysisComplete"] = True
    except Exception as error:
        report["error"] = str(error)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"report": str(args.out.resolve()), "analysisComplete": report["analysisComplete"], "estimatedBpm": report.get("estimatedBpm"), "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["analysisComplete"] else 1


if __name__ == "__main__":
    sys.exit(main())
