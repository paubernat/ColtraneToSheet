"""Render a MIDI file to WAV using FluidSynth + a SoundFont.

The SoundFont (GeneralUser GS, ~30 MB) is auto-downloaded on first use into
``models/soundfonts/`` so the notebook works without manual setup on both
Windows and Colab.

Usage:
    python -m coltrane_to_sheet.midi_player output/song.mid -o output/
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

SOUNDFONT_NAME = "GeneralUserGS.sf2"


def _ensure_fluidsynth_on_path() -> None:
    """On Windows, prepend a bundled FluidSynth bin dir to PATH if present.

    Looks for tools/fluidsynth/**/bin/fluidsynth.exe under the repo root so the
    notebook works without a system-wide install.
    """
    if sys.platform != "win32" or shutil.which("fluidsynth"):
        return
    repo_root = Path(__file__).resolve().parents[2]
    for exe in (repo_root / "tools" / "fluidsynth").rglob("fluidsynth.exe"):
        bin_dir = str(exe.parent)
        if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        return
SOUNDFONT_URLS = [
    "https://schristiancollins.com/soundfonts/GeneralUser_GS_v1.471.zip",
    "https://archive.org/download/free-soundfonts-sf2-2019-04/GeneralUser%20GS%20v1.471.sf2",
]
MIN_SOUNDFONT_BYTES = 1_000_000


def _download(url: str, dest: Path) -> None:
    print(f"Downloading SoundFont from {url} ...")
    with urllib.request.urlopen(url) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)


def ensure_soundfont(soundfont_dir: Path) -> Path:
    """Download GeneralUser GS into soundfont_dir if missing. Return its path."""
    soundfont_dir.mkdir(parents=True, exist_ok=True)
    sf_path = soundfont_dir / SOUNDFONT_NAME

    if sf_path.exists() and sf_path.stat().st_size >= MIN_SOUNDFONT_BYTES:
        return sf_path

    last_err: Exception | None = None
    for url in SOUNDFONT_URLS:
        try:
            tmp = sf_path.with_suffix(".sf2.part")
            _download(url, tmp)
            if tmp.stat().st_size < MIN_SOUNDFONT_BYTES:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"Downloaded file too small: {tmp.stat().st_size} bytes")
            tmp.rename(sf_path)
            return sf_path
        except Exception as e:
            last_err = e
            print(f"  failed: {e}")

    raise RuntimeError(
        f"Could not download a SoundFont. Drop a .sf2 file into {soundfont_dir} "
        f"manually and rename it to {SOUNDFONT_NAME}. Last error: {last_err}"
    )


def midi_to_wav(midi_path: Path, out_dir: Path, soundfont: Path | None = None) -> Path:
    """Render MIDI to WAV using FluidSynth. Returns the WAV path."""
    if not midi_path.exists():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    if soundfont is None:
        soundfont = ensure_soundfont(out_dir.parent / "models" / "soundfonts")
    if not soundfont.exists():
        raise FileNotFoundError(f"SoundFont not found: {soundfont}")

    try:
        from midi2audio import FluidSynth
    except ImportError as e:
        raise ImportError("midi2audio is not installed. Run: pip install midi2audio") from e

    _ensure_fluidsynth_on_path()

    wav_path = out_dir / f"{midi_path.stem}.synth.wav"
    try:
        FluidSynth(sound_font=str(soundfont)).midi_to_audio(str(midi_path), str(wav_path))
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "The 'fluidsynth' binary was not found on PATH.\n"
            "  Windows: download https://github.com/FluidSynth/fluidsynth/releases and "
            "extract into <repo>/tools/fluidsynth/, or run: scoop install fluidsynth\n"
            "  Colab/Linux: !apt-get -qq install fluidsynth\n"
            "  macOS: brew install fluidsynth"
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FluidSynth failed while rendering {midi_path}: {e}") from e

    return wav_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a MIDI file to WAV using FluidSynth.")
    parser.add_argument("midi", type=Path, help="Path to .mid file.")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory.")
    parser.add_argument("--soundfont", type=Path, default=None, help="Optional .sf2 path. Auto-downloaded if omitted.")
    args = parser.parse_args()

    wav = midi_to_wav(args.midi, args.output, soundfont=args.soundfont)
    print(f"Synth WAV written to: {wav}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
