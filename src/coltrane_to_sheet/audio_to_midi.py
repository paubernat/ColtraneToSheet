"""Step 2: Automatic Music Transcription. Isolated piano WAV -> MIDI.

Usage:
    python -m coltrane_to_sheet.audio_to_midi output/song_(Piano).wav -o output/
    python -m coltrane_to_sheet.audio_to_midi output/song_(Piano).wav -o output/ --model basic_pitch
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable


def _transcribe_bytedance(input_wav: Path, output_dir: Path) -> Path:
    """ByteDance High-Resolution Piano Transcription. SOTA on solo piano."""
    import librosa
    import torch
    from piano_transcription_inference import PianoTranscription, sample_rate

    device = "cuda" if torch.cuda.is_available() else "cpu"
    midi_path = output_dir / f"{input_wav.stem}.bytedance.mid"

    # piano-transcription-inference ships its own load_audio that is broken on
    # librosa>=0.10 (calls librosa.core.audio.* which no longer exists). Load
    # the waveform ourselves and pass the numpy array directly.
    audio, _ = librosa.load(str(input_wav), sr=sample_rate, mono=True)
    transcriber = PianoTranscription(device=device, checkpoint_path=None)
    transcriber.transcribe(audio, str(midi_path))
    _embed_detected_tempo(midi_path, audio, sample_rate)
    return midi_path


def _embed_detected_tempo(midi_path: Path, audio, sample_rate: int) -> float | None:
    """Estimate tempo from the audio and rewrite the MIDI's set_tempo + tick deltas.

    ByteDance always writes the MIDI at a default tempo (120 BPM). We replace
    that with the librosa estimate and rescale every event's delta time so the
    absolute timing of every note in seconds is preserved. The result: notes
    that were a 16th in the real recording now occupy a clean 0.25-quarter
    offset in the MIDI, which makes downstream quantization in
    :mod:`midi_to_sheet` actually align to the beat grid.
    """
    import librosa
    import mido
    import numpy as np

    try:
        tempo_arr, _ = librosa.beat.beat_track(y=audio, sr=sample_rate)
        bpm = float(np.atleast_1d(tempo_arr)[0])
    except Exception as e:
        print(f"  tempo detection failed ({e}); leaving MIDI tempo at default.")
        return None
    if not (30.0 <= bpm <= 300.0):
        print(f"  tempo detection out of range ({bpm:.1f}); leaving MIDI tempo at default.")
        return None

    new_tempo_us = mido.bpm2tempo(bpm)
    mid = mido.MidiFile(str(midi_path))

    old_tempo_us = 500_000  # MIDI spec default = 120 BPM
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                old_tempo_us = msg.tempo
                break
        else:
            continue
        break

    scale = old_tempo_us / new_tempo_us
    for track in mid.tracks:
        for i, msg in enumerate(track):
            new_msg = msg
            if msg.time:
                new_msg = new_msg.copy(time=int(round(msg.time * scale)))
            if msg.type == "set_tempo":
                new_msg = new_msg.copy(tempo=new_tempo_us)
            track[i] = new_msg

    mid.save(str(midi_path))
    print(f"Detected tempo: {bpm:.1f} BPM (embedded in {midi_path.name})")
    return bpm


def _transcribe_basic_pitch(input_wav: Path, output_dir: Path) -> Path:
    """Spotify basic-pitch. Lighter, multi-instrument capable, less accurate on dense piano."""
    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

    predict_and_save(
        audio_path_list=[str(input_wav)],
        output_directory=str(output_dir),
        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=False,
        model_or_model_path=ICASSP_2022_MODEL_PATH,
    )
    midi_path = output_dir / f"{input_wav.stem}_basic_pitch.mid"
    if not midi_path.exists():
        candidates = list(output_dir.glob(f"{input_wav.stem}*basic_pitch*.mid"))
        if not candidates:
            raise RuntimeError(f"basic-pitch did not produce a MIDI file in {output_dir}")
        midi_path = candidates[0]
    return midi_path


MODELS: dict[str, Callable[[Path, Path], Path]] = {
    "bytedance": _transcribe_bytedance,
    "basic_pitch": _transcribe_basic_pitch,
}


def audio_to_midi(
    input_path: Path,
    output_dir: Path,
    model_key: str = "bytedance",
) -> Path:
    """Transcribe a piano WAV to MIDI and return the MIDI path."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if model_key not in MODELS:
        raise ValueError(f"Unknown model '{model_key}'. Choose from {sorted(MODELS)}.")

    output_dir.mkdir(parents=True, exist_ok=True)
    return MODELS[model_key](input_path, output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe a piano audio file to MIDI.")
    parser.add_argument("input", type=Path, help="Path to isolated piano WAV (output of Step 1).")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory.")
    parser.add_argument(
        "--model",
        choices=sorted(MODELS.keys()),
        default="bytedance",
        help="AMT model. bytedance is the default; basic_pitch is a CPU-friendly fallback.",
    )
    args = parser.parse_args()

    midi_path = audio_to_midi(
        input_path=args.input,
        output_dir=args.output,
        model_key=args.model,
    )
    print(f"MIDI written to: {midi_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
