# ColtraneToSheet

Jazz audio → readable sheet music. A 3-step Python pipeline:

1. **Source Separation** (`audio-separator`, BS-RoFormer 6-stem) — isolate the piano.
2. **Automatic Music Transcription** (ByteDance piano-transcription) — piano WAV → MIDI.
3. **Notation & Rendering** (`music21` + MuseScore) — quantize swing, render PDF.

```
    .--.--.--.--.--.--.--.--.--.
    |  |  |  |  |  |  |  |  |  |
    |  |  |  |  |  |  |  |  |  |
    | _| _| _| _| _| _| _| _|  |
    ||# ||# ||# ||# ||# ||# ||# ||
    ||# ||# ||# ||# ||# ||# ||# ||
    ||__||__||__||__||__||__||__||
    |   |   |   |   |   |   |   |
    |   |   |   |   |   |   |   |
    | C | D | E | F | G | A | B |
    |___|___|___|___|___|___|___|
           ~~~ AI did nasty work on what piano is... 
```

## Setup (local, .venv)

```powershell
# From the repo root
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-cpu.txt
```

If you don't have Python yet, install **Python 3.11** from python.org (3.12 also works; some torch wheels lag behind on 3.13). Verify with `python --version`.

## Setup (Colab, GPU)

Open `notebooks/01_source_separation.ipynb` in Colab, switch runtime to **T4 GPU**, and run all cells. The first cell has the `pip install` command commented out — uncomment it.

## Usage — Step 1 (source separation)

1. Drop a jazz audio file into `input/` (e.g. `input/coltrane.mp3`).
2. Either:
   - Open `notebooks/01_source_separation.ipynb` and edit `INPUT_FILENAME`, or
   - Run the CLI: `python -m coltrane_to_sheet.separate input/coltrane.mp3 -o output/`
3. The isolated piano stem lands in `output/`.

## Usage — Step 2 (audio → MIDI)

Prereq: install the **FluidSynth binary** (only needed for MIDI playback):
- Windows: `winget install --id FluidSynth.FluidSynth` (or `scoop install fluidsynth`)
- Colab/Linux: `apt-get install fluidsynth`
- macOS: `brew install fluidsynth`

Then:
- CLI: `python -m coltrane_to_sheet.audio_to_midi "output/song_(Piano).wav" -o output/`
- Or open `notebooks/02_audio_to_midi.ipynb` — auto-picks the latest piano stem from `output/`, transcribes, and plays back the synthesized MIDI alongside the original mix and piano stem so you can A/B/C by ear.

Default model is **ByteDance** piano-transcription (SOTA on solo piano). Toggle with `--model basic_pitch` for a CPU-friendlier alternative.

## Usage — Step 3 (MIDI → sheet music PDF)

Prereq: install **MuseScore** (used by `music21` to render MusicXML → PDF):
- Windows: `winget install --id MuseScore.MuseScore`
- Colab/Linux: `apt-get install -y musescore3`
- macOS: `brew install --cask musescore`

Then:
- CLI: `python -m coltrane_to_sheet.midi_to_sheet "output/song.bytedance.mid" -o output/`
- Or open `notebooks/03_midi_to_sheet.ipynb` — auto-picks the latest `.mid` from `output/`, quantizes to 16ths, splits the grand staff at middle C, writes MusicXML + PDF, and previews the PDF inline.

Useful flags: `--tempo 140`, `--time-signature 3/4`, `--no-swing`, `--split-pitch 60`, `--quantum 4` (16ths) or `--quantum 2` (8ths), `--no-pdf` (MusicXML only). If MuseScore is missing the CLI still produces MusicXML and prints install instructions.
