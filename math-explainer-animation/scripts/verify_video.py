#!/usr/bin/env python3
"""Inspect the encoded delivery, not Remotion source frames.

python verify_video.py output/trial.mp4 --out qa/trial --fps 30 --width 1080 --height 1920 --require-audio
FFmpeg/FFprobe: --ffmpeg/--ffprobe, FFMPEG_BINARY/FFPROBE_BINARY, or PATH.
numpy enables numeric PCM checks; Pillow enables phone previews/contact sheets.
Passing this script does not establish mathematical, visual or audible quality.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def executable(explicit, env, name):
    value = explicit or os.environ.get(env) or shutil.which(name)
    if value and (found := shutil.which(value)):
        return found
    if value and Path(value).is_file():
        return str(Path(value).resolve())
    raise RuntimeError(f"{name} not found. Set --{name}, {env}, or PATH.")


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def rate(value):
    try:
        return float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None


def finite_number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def audio_metrics(binary, path, out):
    import numpy as np
    log = out / "audio-pcm-decode.log"
    peak, count, clipped, square_sum = 0.0, 0, 0, 0.0
    nonfinite = 0
    # Decode all samples, streaming small blocks rather than keeping a feature
    # film in memory. Stereo/48 kHz is this analysis representation only.
    with log.open("wb") as stderr:
        process = subprocess.Popen([binary, "-v", "error", "-xerror", "-i", str(path), "-map", "0:a:0", "-ac", "2", "-ar", "48000", "-f", "f32le", "-"], stdout=subprocess.PIPE, stderr=stderr)
        remainder = b""
        try:
            while block := process.stdout.read(256 * 1024):
                block = remainder + block
                usable = len(block) // 4 * 4
                remainder = block[usable:]
                values = np.frombuffer(block[:usable], dtype="<f4")
                nonfinite += int(np.count_nonzero(~np.isfinite(values)))
                finite = values[np.isfinite(values)].astype(np.float64)
                if len(finite):
                    peak = max(peak, float(np.abs(finite).max()))
                    clipped += int(np.count_nonzero(np.abs(finite) >= 1.0))
                    square_sum += float(np.dot(finite, finite))
                    count += len(finite)
            code = process.wait()
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
    if code or remainder:
        raise RuntimeError("Audio PCM decode failed; inspect audio-pcm-decode.log")
    return {"decodedRepresentation": "48 kHz, stereo float32; not necessarily the original stream format",
            "sampleValues": count, "samplesAtOrAboveFullScale": clipped, "nonfiniteSamples": nonfinite,
            "peakLinear": peak, "samplePeakDbfs": 20 * math.log10(peak) if peak else None,
            "rmsDbfs": 10 * math.log10(square_sum / count) if square_sum and count else None,
            "allSamplesDecoded": True,
            "limitation": "Full-scale sample counting detects a possible overload, not every form of audible clipping or distortion."}


def extract_frames(binary, path, out, frames):
    destination = out / "encoded-frames"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    # Each extraction decodes the actual MP4 by frame number. Separate commands
    # avoid ambiguous output numbering when a requested frame is unavailable.
    for frame in frames:
        target = destination / f"frame-{frame:06d}.png"
        command = [binary, "-v", "error", "-y", "-i", str(path), "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", "-update", "1", str(target)]
        result = subprocess.run(command, capture_output=True)
        if result.returncode or not target.is_file() or not target.stat().st_size:
            raise RuntimeError(f"Encoded frame {frame} extraction failed: {result.stderr.decode('utf8', errors='replace')[-1000:]}")
        records.append({"frame": frame, "file": str(target.resolve()), "sha256": digest(target)})
    return records


def make_previews(records, out, phone_width, columns):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return {"created": False, "reason": "Pillow is unavailable; encoded PNGs were still extracted. Install requirements.txt for previews."}
    phones = out / "phone-previews"
    phones.mkdir(exist_ok=True)
    thumbs = []
    preview_paths = []
    for record in records:
        with Image.open(record["file"]) as image:
            image = image.convert("RGB")
            height = max(1, round(image.height * phone_width / image.width))
            phone = image.resize((phone_width, height), Image.Resampling.LANCZOS)
            target = phones / f"phone-{record['frame']:06d}.png"
            phone.save(target)
            preview_paths.append(str(target.resolve()))
            thumbnail = image.copy()
            thumbnail.thumbnail((270, 480), Image.Resampling.LANCZOS)
            thumbs.append(thumbnail)
    tile_width = 286
    tile_height = max(image.height for image in thumbs) + 44
    columns = min(columns, len(thumbs))
    sheet = Image.new("RGB", (columns * tile_width, math.ceil(len(thumbs) / columns) * tile_height), "#101B28")
    draw = ImageDraw.Draw(sheet)
    for index, (record, thumbnail) in enumerate(zip(records, thumbs)):
        x, y = index % columns * tile_width, index // columns * tile_height
        draw.text((x + 8, y + 8), f"frame {record['frame']}", fill="white")
        sheet.paste(thumbnail, (x + (tile_width - thumbnail.width) // 2, y + 32))
    target = out / "contact-sheet.jpg"
    sheet.save(target, quality=93)
    return {"created": True, "phoneWidth": phone_width, "phoneFiles": preview_paths,
            "contactSheet": str(target.resolve()), "manualVisualReviewComplete": False,
            "limitation": "Resizing to phone width is not a physical phone test."}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=Path("qa/video"), help="QA directory; avoid reusing it for a different movie")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    parser.add_argument("--fps", type=float, help="Expected avg/nominal frame-rate metadata; not a per-frame PTS proof of constant timing")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--duration", type=float, help="Expected video duration in seconds, tolerance one frame")
    parser.add_argument("--frames", help="Comma-separated encoded video frame numbers; default 8 evenly spaced frames")
    parser.add_argument("--require-audio", action="store_true", help="Fail if no audio stream; omit for intentional silent trials")
    parser.add_argument("--video-codec", default="h264", help="Expected codec; use any to skip compatibility gate")
    parser.add_argument("--pixel-format", default="yuv420p", help="Expected pixel format; use any to skip")
    parser.add_argument("--audio-codec", default="aac", help="Expected audio codec when present; use any to skip")
    parser.add_argument("--max-true-peak-dbfs", type=float, default=0.0, help="Peak gate, not a platform loudness target")
    parser.add_argument("--phone-width", type=int, default=390)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()
    if any(value is not None and value <= 0 for value in [args.fps, args.width, args.height, args.duration, args.phone_width, args.columns]):
        parser.error("Expected dimensions, fps, duration and preview sizes must be positive")
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"technicalPass": False, "file": str(args.video.resolve()), "failures": [], "warnings": [],
              "manualReview": {"mathematicalContent": False, "visualLayoutAndCaptions": False, "fullListening": False, "physicalPhone": False, "platformUpload": False},
              "scope": "Encoded media technical checks and extracted previews only. No full quality approval is implied.",
              "frameRateCheckScope": "avg_frame_rate and r_frame_rate metadata only; per-frame PTS spacing is not inspected and constant timing is not proved."}
    try:
        if not args.video.is_file():
            raise FileNotFoundError(f"Completed movie does not exist: {args.video}")
        ffmpeg = executable(args.ffmpeg, "FFMPEG_BINARY", "ffmpeg")
        ffprobe = executable(args.ffprobe, "FFPROBE_BINARY", "ffprobe")
        report.update(bytes=args.video.stat().st_size, sha256=digest(args.video))
        probed = subprocess.run([ffprobe, "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(args.video)], capture_output=True, text=True, encoding="utf8")
        if probed.returncode:
            raise RuntimeError("FFprobe failed: " + probed.stderr[-2000:])
        metadata = json.loads(probed.stdout)
        (args.out / "ffprobe.json").write_text(json.dumps(metadata, indent=2), encoding="utf8")
        videos = [stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")]
        audios = [stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "audio"]
        if not videos:
            raise RuntimeError("No video stream found")
        video = videos[0]
        fps = rate(video.get("avg_frame_rate")) or rate(video.get("r_frame_rate"))
        if not fps or fps <= 0:
            raise RuntimeError("Could not determine a positive video frame rate")
        total_frames = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
        seconds = finite_number(video.get("duration")) or finite_number(metadata.get("format", {}).get("duration"))
        report["video"] = {"codec": video.get("codec_name"), "pixelFormat": video.get("pix_fmt"), "width": video.get("width"), "height": video.get("height"), "fps": fps, "decodedFrameCount": total_frames, "durationSeconds": seconds}
        if total_frames <= 0:
            report["failures"].append("FFprobe did not count any decoded video frames")
        for label, expected, actual in [("width", args.width, video.get("width")), ("height", args.height, video.get("height"))]:
            if expected is not None and expected != actual:
                report["failures"].append(f"Expected {label} {expected}, got {actual}")
        for label, expected, actual in [("video codec", args.video_codec, video.get("codec_name")), ("pixel format", args.pixel_format, video.get("pix_fmt"))]:
            if expected != "any" and expected != actual:
                report["failures"].append(f"Expected {label} {expected}, got {actual}")
        if args.fps is not None and (abs(fps - args.fps) > 0.001 or abs((rate(video.get("r_frame_rate")) or fps) - args.fps) > 0.001):
                report["failures"].append(f"Expected {args.fps} fps metadata, got avg={video.get('avg_frame_rate')}, nominal={video.get('r_frame_rate')}")
        if args.duration is not None and (seconds is None or abs(seconds - args.duration) > 1 / fps + 1e-5):
            report["failures"].append(f"Duration differs from expected {args.duration} seconds by more than one frame")
        # Explicit maps make this a full decode of every A/V stream.
        decoded = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-i", str(args.video), "-map", "0:v?", "-map", "0:a?", "-f", "null", "-"], capture_output=True)
        (args.out / "full-decode.log").write_bytes(decoded.stderr)
        report["fullAvDecode"] = {"exitCode": decoded.returncode, "errorLogBytes": len(decoded.stderr), "passed": decoded.returncode == 0 and not decoded.stderr}
        if not report["fullAvDecode"]["passed"]:
            report["failures"].append("Full A/V decode reported an error; inspect full-decode.log")
        report["audioPresent"] = bool(audios)
        if args.require_audio and not audios:
            report["failures"].append("Audio was required but no audio stream is present")
        if len(audios) > 1:
            report["warnings"].append("Multiple audio streams: numeric loudness/PCM checks use the first; full decode includes all")
        if audios:
            audio = audios[0]
            report["audio"] = {"codec": audio.get("codec_name"), "sampleRate": audio.get("sample_rate"), "channels": audio.get("channels")}
            if args.audio_codec != "any" and audio.get("codec_name") != args.audio_codec:
                report["failures"].append(f"Expected audio codec {args.audio_codec}, got {audio.get('codec_name')}")
            try:
                report["audio"]["pcm"] = audio_metrics(ffmpeg, args.video, args.out)
                pcm = report["audio"]["pcm"]
                if pcm["nonfiniteSamples"] or pcm["samplesAtOrAboveFullScale"]:
                    report["failures"].append("Non-finite or full-scale samples detected; inspect audio before delivery")
                if pcm["peakLinear"] == 0:
                    report["warnings"].append("Audio stream is silent")
            except ImportError:
                report["failures"].append("numpy unavailable: sample peak/clipping check not performed; install requirements.txt")
                report["audio"]["pcm"] = {"allSamplesDecoded": False, "reason": "numpy unavailable"}
            loudness = subprocess.run([ffmpeg, "-hide_banner", "-i", str(args.video), "-map", "0:a:0", "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, encoding="utf8", errors="replace")
            (args.out / "loudness.log").write_text(loudness.stderr, encoding="utf8")
            summary = loudness.stderr.rsplit("Summary:", 1)[-1]
            integrated = re.search(r"\bI:\s*([-+\w.]+)\s*LUFS", summary)
            peak = re.search(r"Peak:\s*([-+\w.]+)\s*dBFS", summary)
            integrated_value = finite_number(integrated.group(1)) if integrated else None
            peak_value = finite_number(peak.group(1)) if peak else None
            report["audio"].update(integratedLufs=integrated_value, truePeakDbfs=peak_value, loudnessMeasured=loudness.returncode == 0 and integrated is not None and peak is not None)
            if not report["audio"]["loudnessMeasured"]:
                report["failures"].append("EBU R128 measurement unavailable; inspect loudness.log")
            if peak_value is not None and peak_value > args.max_true_peak_dbfs:
                report["failures"].append(f"True peak {peak_value} dBFS exceeds configured {args.max_true_peak_dbfs} dBFS")
            report["audio"]["limitation"] = "Loudness/peak measurements do not establish intelligibility, music suitability, click-free edits, or listening quality. No universal platform loudness target is assumed."
        if total_frames <= 0:
            raise RuntimeError("Cannot extract frames without a decoded frame count")
        if args.frames:
            frames = sorted(set(int(value.strip()) for value in args.frames.split(",")))
        else:
            frames = sorted(set(round(i * (total_frames - 1) / 7) for i in range(8)))
        if not frames or any(frame < 0 or frame >= total_frames for frame in frames):
            raise ValueError(f"Requested keyframes must be in [0, {total_frames - 1}]")
        report["keyframes"] = extract_frames(ffmpeg, args.video, args.out, frames)
        for record in report["keyframes"]:
            record["seconds"] = record["frame"] / fps
        report["previews"] = make_previews(report["keyframes"], args.out, args.phone_width, args.columns)
        report["technicalPass"] = not report["failures"]
    except Exception as error:
        report["failures"].append(str(error))
    target = args.out / "video-check.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"report": str(target.resolve()), "technicalPass": report["technicalPass"], "failures": report["failures"], "warnings": report["warnings"]}, ensure_ascii=False))
    return 0 if report["technicalPass"] else 1


if __name__ == "__main__":
    sys.exit(main())
