"""Step 1: Source separation. Isolate the piano stem from a mixed audio file.

Usage:
    python -m coltrane_to_sheet.separate input/song.mp3 -o output/
    python -m coltrane_to_sheet.separate input/song.mp3 -o output/ --model htdemucs_6s
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from audio_separator.separator import Separator


MODELS = {
    "bs_roformer": "BS-RoFormer-SW-Fixed.ckpt",   
    "htdemucs_6s": "htdemucs_6s.yaml",
}


def separate_piano(
    input_path: Path,
    output_dir: Path,
    model_key: str = "bs_roformer",
    model_dir: Path | None = None,
) -> Path:
    """Run source separation and return the path to the isolated piano stem."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    model_filename = MODELS[model_key]

    separator = Separator(
        output_dir=str(output_dir),
        model_file_dir=str(model_dir) if model_dir else "models",
        output_format="WAV",
    )
    separator.load_model(model_filename=model_filename)

    output_files = separator.separate(str(input_path))
    output_paths = [Path(output_dir) / f for f in output_files]

    piano_stem = next(
        (p for p in output_paths if "piano" in p.name.lower()),
        None,
    )
    if piano_stem is None:
        raise RuntimeError(
            f"No piano stem found in outputs. Got: {[p.name for p in output_paths]}"
        )
    return piano_stem


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolate piano stem from a mixed audio file.")
    parser.add_argument("input", type=Path, help="Path to input audio file (mp3/wav/flac).")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory.")
    parser.add_argument(
        "--model",
        choices=sorted(MODELS.keys()),
        default="bs_roformer",
        help="Separation model. bs_roformer is the default; htdemucs_6s is a faster fallback.",
    )
    parser.add_argument("--model-dir", type=Path, default=Path("models"), help="Where to cache model checkpoints.")
    args = parser.parse_args()

    piano_stem = separate_piano(
        input_path=args.input,
        output_dir=args.output,
        model_key=args.model,
        model_dir=args.model_dir,
    )
    print(f"Piano stem written to: {piano_stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
