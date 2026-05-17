"""End-to-end pipeline: mixed audio -> piano stem -> MIDI -> sheet PDF.

Usage:
    python run.py input/coltrane.mp3
    python run.py input/coltrane.mp3 --sep-model htdemucs_6s

Outputs land in ``output/{input_stem}_{sep_model}/``.

On first run, missing dependencies are installed automatically into the active
Python environment: ``requirements.txt`` if an NVIDIA GPU is detected,
otherwise ``requirements-cpu.txt``.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
SEP_MODEL_CHOICES = ("bs_roformer", "htdemucs_6s")


def _has_gpu() -> bool:
    return shutil.which("nvidia-smi") is not None


def _ensure_deps() -> None:
    """Install requirements on first run if the key pipeline packages are missing."""
    try:
        import audio_separator  # noqa: F401
        import piano_transcription_inference  # noqa: F401
        import music21  # noqa: F401
        return
    except ImportError:
        pass

    req_file = "requirements.txt" if _has_gpu() else "requirements-cpu.txt"
    req_path = REPO_ROOT / req_file
    print(f"Installing dependencies from {req_file} (one-time setup)...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(req_path)]
    )


def main(input_path: Path, sep_model: str = "bs_roformer") -> Path:
    _ensure_deps()
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from coltrane_to_sheet.separate import separate_piano
    from coltrane_to_sheet.audio_to_midi import audio_to_midi
    from coltrane_to_sheet.midi_to_sheet import midi_to_sheet

    input_path = Path(input_path)
    run_dir = Path("output") / f"{input_path.stem}_{sep_model}"
    run_dir.mkdir(parents=True, exist_ok=True)

    piano_wav = separate_piano(
        input_path=input_path,
        output_dir=run_dir,
        model_key=sep_model,
        model_dir=Path("models"),
    )
    midi_path = audio_to_midi(piano_wav, run_dir, model_key="bytedance")
    return midi_to_sheet(midi_path, run_dir)


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Mixed audio file (mp3/wav/flac).")
    parser.add_argument(
        "--sep-model",
        choices=SEP_MODEL_CHOICES,
        default="bs_roformer",
        help="Source-separation model (default: bs_roformer).",
    )
    args = parser.parse_args()
    out = main(args.input, args.sep_model)
    print(f"\nDone. Output: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
