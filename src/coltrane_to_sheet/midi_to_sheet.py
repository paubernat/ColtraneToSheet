"""Step 3: MIDI -> readable sheet music (MusicXML + optional PDF).

The MIDI from Step 2 (ByteDance AMT) is unquantized, has no tempo/meter, and
crams all 88 keys onto a single staff. This module quantizes it, splits it into
a grand staff (LH/RH by pitch), and renders to MusicXML + (optionally) PDF via
the MuseScore CLI.

Usage:
    python -m coltrane_to_sheet.midi_to_sheet output/song.bytedance.mid -o output/
    python -m coltrane_to_sheet.midi_to_sheet output/song.bytedance.mid -o output/ \\
        --tempo 140 --time-signature 3/4 --no-swing --split-pitch 60
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _ensure_musescore_configured() -> Path | None:
    """Locate MuseScore and register it with music21. Returns the binary path or None."""
    candidates: list[Path] = []

    for name in ("mscore", "musescore", "MuseScore4", "MuseScore3"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    if sys.platform == "win32":
        program_files = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" if os.environ.get("LOCALAPPDATA") else None,
        ]
        for base in filter(None, program_files):
            for sub in ("MuseScore 4", "MuseScore 3"):
                for exe in ("MuseScore4.exe", "MuseScore3.exe", "mscore.exe"):
                    p = base / sub / "bin" / exe
                    if p.exists():
                        candidates.append(p)
    elif sys.platform == "darwin":
        for app in ("MuseScore 4.app", "MuseScore 3.app"):
            p = Path("/Applications") / app / "Contents" / "MacOS" / "mscore"
            if p.exists():
                candidates.append(p)

    if not candidates:
        return None

    binary = candidates[0]
    try:
        from music21 import environment
        us = environment.UserSettings()
        us["musicxmlPath"] = str(binary)
        us["musescoreDirectPNGPath"] = str(binary)
    except Exception as e:
        print(f"  warning: could not register MuseScore with music21: {e}")

    return binary


def _split_grand_staff(part, split_pitch: int):
    """Split a single Part into (right_hand, left_hand) Parts at the given MIDI pitch.

    Notes that share a quantized onset are merged into one chord, and each
    chord's duration is clamped so it ends no later than the next onset in the
    same hand. Without this, AMT's overlapping note releases make
    ``makeNotation`` spawn a new voice for every overlap (we saw 20+ voices per
    staff), which MuseScore renders as a near-empty PDF. The clamp-and-merge
    pass collapses each hand into a clean monophonic-with-chords line — the
    standard piano-transcription reduction.
    """
    from music21 import chord, clef, instrument, note, pitch as pitch_mod, stream

    by_hand: dict[str, dict[float, dict[int, float]]] = {"rh": {}, "lh": {}}

    for elem in part.flatten().notes:
        offset = float(elem.offset)
        ql = float(elem.quarterLength)
        if isinstance(elem, note.Note):
            pitches = [elem.pitch]
        elif isinstance(elem, chord.Chord):
            pitches = list(elem.pitches)
        else:
            continue
        for p in pitches:
            hand = "rh" if p.midi >= split_pitch else "lh"
            bucket = by_hand[hand].setdefault(offset, {})
            if ql > bucket.get(p.midi, 0.0):
                bucket[p.midi] = ql

    def _build(events: dict[float, dict[int, float]], clef_obj, part_id: str):
        out = stream.Part(id=part_id)
        out.insert(0, instrument.Piano())
        out.insert(0, clef_obj)
        offsets = sorted(events)
        for i, off in enumerate(offsets):
            entry = events[off]
            ql = max(entry.values())
            if i + 1 < len(offsets):
                ql = min(ql, offsets[i + 1] - off)
            if ql <= 0:
                continue
            pitches = [pitch_mod.Pitch(midi=m) for m in sorted(entry)]
            if len(pitches) == 1:
                out.insert(off, note.Note(pitches[0], quarterLength=ql))
            else:
                out.insert(off, chord.Chord(pitches, quarterLength=ql))
        return out

    rh = _build(by_hand["rh"], clef.TrebleClef(), "RH")
    lh = _build(by_hand["lh"], clef.BassClef(), "LH")
    return rh, lh


def _read_midi_tempo(midi_path: Path) -> float | None:
    """Return the first set_tempo (in BPM) from the MIDI, or None if absent."""
    try:
        import mido
    except ImportError:
        return None
    try:
        mid = mido.MidiFile(str(midi_path))
    except Exception:
        return None
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                return float(mido.tempo2bpm(msg.tempo))
    return None


def midi_to_sheet(
    midi_path: Path,
    output_dir: Path,
    *,
    tempo: int | float | None = None,
    time_signature: str = "4/4",
    swing: bool = True,
    split_pitch: int = 60,
    quantum_divisor: int = 4,
    title: str | None = None,
    render_pdf: bool = True,
) -> Path:
    """MIDI -> MusicXML (+PDF). Returns the PDF path if rendered, else MusicXML path.

    When ``tempo`` is None, the BPM is read from the MIDI's set_tempo event
    (which :func:`audio_to_midi` embeds from a librosa estimate); falls back to
    120 BPM if no tempo is present in the file.
    """
    if not midi_path.exists():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    from music21 import converter, expressions, metadata, meter, stream, tempo as tempo_mod

    if tempo is None:
        tempo = _read_midi_tempo(midi_path) or 120
        print(f"Tempo (read from MIDI): {tempo:.1f} BPM")
    else:
        print(f"Tempo (overridden): {tempo} BPM")

    print(f"Loading MIDI: {midi_path}")
    parsed = converter.parse(str(midi_path), quantizePost=False)

    flat_part = stream.Part()
    for elem in parsed.flatten().notesAndRests:
        flat_part.insert(elem.offset, elem)

    print(f"Quantizing to 1/{quantum_divisor} of a quarter note...")
    flat_part.quantize(
        quarterLengthDivisors=(quantum_divisor,),
        processOffsets=True,
        processDurations=True,
        recurse=True,
        inPlace=True,
    )

    print(f"Splitting grand staff at MIDI pitch {split_pitch}...")
    rh, lh = _split_grand_staff(flat_part, split_pitch)

    rh.insert(0, tempo_mod.MetronomeMark(number=tempo))
    rh.insert(0, meter.TimeSignature(time_signature))
    lh.insert(0, meter.TimeSignature(time_signature))
    if swing:
        rh.insert(0, expressions.TextExpression("Swing"))

    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    score.metadata = metadata.Metadata()
    score.metadata.title = title or midi_path.stem
    score.metadata.composer = "AMT transcription"

    print("Building notation (measures, beams, rests)...")
    score.makeNotation(inPlace=True)

    musicxml_path = output_dir / f"{midi_path.stem}.musicxml"
    print(f"Writing MusicXML: {musicxml_path}")
    score.write("musicxml", fp=str(musicxml_path))

    if not render_pdf:
        return musicxml_path

    pdf_path = _render_pdf(score, musicxml_path, output_dir)
    return pdf_path or musicxml_path


def _try_musescore_cli(binary: Path, musicxml_path: Path, pdf_path: Path) -> bool:
    """Run `musescore -o pdf xml`. Returns True on success. Prints stderr on failure."""
    try:
        # -f/--force: ignore warnings about the score (MuseScore otherwise
        # exits non-zero on the AMT-quantized notation we hand it).
        result = subprocess.run(
            [str(binary), "-f", "-o", str(pdf_path), str(musicxml_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and pdf_path.exists():
            print(f"PDF written to: {pdf_path}")
            return True
        err = (result.stderr or result.stdout or "").strip()
        print(f"  MuseScore CLI exit {result.returncode}: {err or '(no stderr output)'}")
    except FileNotFoundError as e:
        print(f"  MuseScore binary not found: {e}")
    return False


def _render_pdf(score, musicxml_path: Path, output_dir: Path) -> Path | None:
    """Render score -> PDF via MuseScore. Returns the PDF path, or None on failure."""
    binary = _ensure_musescore_configured()
    pdf_path = output_dir / f"{musicxml_path.stem}.pdf"

    if binary is not None:
        try:
            print(f"Rendering PDF via {binary.name}...")
            score.write("musicxml.pdf", fp=str(pdf_path))
            if pdf_path.exists():
                print(f"PDF written to: {pdf_path}")
                return pdf_path
        except Exception as e:
            print(f"  music21->MuseScore handoff failed ({e}); falling back to direct CLI.")
        if _try_musescore_cli(binary, musicxml_path, pdf_path):
            return pdf_path

    print(
        "\nCould not render PDF. Install MuseScore and re-run, or open the MusicXML directly:\n"
        "  Windows: winget install --id MuseScore.MuseScore\n"
        "  Colab/Linux: !apt-get install -y musescore3\n"
        "  macOS: brew install --cask musescore\n"
        f"  MusicXML: {musicxml_path}\n"
    )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a MIDI file to a sheet-music PDF.")
    parser.add_argument("input", type=Path, help="Path to .mid file (output of Step 2).")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"), help="Output directory.")
    parser.add_argument("--tempo", type=float, default=None, help="Beats per minute. Default: read from MIDI's set_tempo (embedded by audio_to_midi).")
    parser.add_argument("--time-signature", default="4/4", help="e.g. 4/4, 3/4, 6/8 (default: 4/4).")
    parser.add_argument("--no-swing", action="store_true", help="Omit the 'Swing' tempo marking.")
    parser.add_argument("--split-pitch", type=int, default=60, help="MIDI pitch threshold for RH/LH (default: 60 = middle C).")
    parser.add_argument("--quantum", type=int, default=4, help="Quantization divisor of a quarter note (4 = 16ths, default).")
    parser.add_argument("--title", default=None, help="Score title (default: MIDI filename stem).")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF rendering; write only MusicXML.")
    args = parser.parse_args()

    out = midi_to_sheet(
        midi_path=args.input,
        output_dir=args.output,
        tempo=args.tempo,
        time_signature=args.time_signature,
        swing=not args.no_swing,
        split_pitch=args.split_pitch,
        quantum_divisor=args.quantum,
        title=args.title,
        render_pdf=not args.no_pdf,
    )
    print(f"\nDone. Output: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
