# File guide

A map of every file/folder in the repo and what it's for.

## Top level

| Path | Purpose |
| --- | --- |
| `run.py` | End-to-end orchestrator. Chains the three pipeline stages: `main(input_path, sep_model)` → `output/{input_stem}_{sep_model}/{piano.wav, .mid, .musicxml, .pdf}`. The single entry point most users want. |
| `README.md` | Project overview, install instructions (local venv + Colab), and per-step CLI usage examples. |
| `requirements.txt` | Full deps — GPU build of `audio-separator` on non-macOS. Use this on Colab/Linux with CUDA. |
| `requirements-cpu.txt` | CPU-only build of `audio-separator`. Use this on Windows/macOS without a GPU. |
| `.python-version` | Pins Python 3.11 for `pyenv` / `py -3.11`. |
| `.gitignore` | Ignores `.venv/`, caches, `models/`, `output/`, and large audio files in `input/` (keeps `.gitkeep` markers). |

## `src/coltrane_to_sheet/` — pipeline modules

Each module is independently runnable as `python -m coltrane_to_sheet.<name>` and exposes a single primary function that `run.py` imports.

| File | Purpose |
| --- | --- |
| `__init__.py` | Empty marker — makes `coltrane_to_sheet` an importable package. |
| `separate.py` | **Step 1**: source separation. `separate_piano(input, out_dir, model_key)` returns the path to the isolated piano stem. Supports two models via the `MODELS` dict: `bs_roformer` (default, BS-RoFormer 6-stem, ~400 MB, high quality) and `htdemucs_6s` (Demucs 6-stem, ~55 MB, faster, weaker on piano). |
| `audio_to_midi.py` | **Step 2**: automatic music transcription. `audio_to_midi(piano_wav, out_dir, model_key)` returns the MIDI path. Two models: `bytedance` (default, SOTA on solo piano) and `basic_pitch` (Spotify, CPU-friendlier). Also runs librosa beat-tracking to embed a detected tempo + rescale tick deltas so downstream quantization aligns to the grid. |
| `midi_to_sheet.py` | **Step 3**: notation. `midi_to_sheet(midi, out_dir, **kwargs)` quantizes the MIDI, splits the grand staff at a pitch threshold (default middle C), adds tempo/meter/Swing marking, writes MusicXML, and renders PDF via the MuseScore CLI. Returns the PDF (or MusicXML if PDF render fails / `--no-pdf`). |
| `midi_player.py` | Bonus: `midi_to_wav(midi, out_dir)` synthesizes a MIDI back to WAV using FluidSynth + the GeneralUser GS SoundFont (auto-downloaded into `models/soundfonts/` on first use). Used by the audio-to-midi notebook for A/B/C ear-checks; not part of the `run.py` pipeline. |

## `notebooks/` — interactive equivalents

Mirror the three pipeline stages with playback, inline PDF preview, and the Colab GPU setup cell. Functionally redundant with `run.py` + the modules — kept around for the Colab path and ear-checking.

| File | Purpose |
| --- | --- |
| `01_source_separation.ipynb` | Step 1 in notebook form. The README points Colab users here for free T4 GPU access. |
| `02_audio_to_midi.ipynb` | Step 2 in notebook form. Auto-picks the latest piano stem and plays the synthesized MIDI alongside the original mix and piano stem so you can A/B/C by ear. |
| `03_midi_to_sheet.ipynb` | Step 3 in notebook form. Auto-picks the latest `.mid` and previews the rendered PDF inline. |

## Data / asset directories

| Path | Purpose |
| --- | --- |
| `input/` | Drop source audio (mp3/wav/flac) here. `.gitkeep` only — actual audio is gitignored. |
| `output/` | All pipeline outputs land here. `run.py` creates a per-run subfolder `{input_stem}_{sep_model}/` containing the piano stem, intermediate `.mid` + `.musicxml`, and the final `.pdf`. Gitignored. |
| `models/` | Auto-populated cache for separation checkpoints (`model_bs_roformer_*.ckpt`, `htdemucs_6s.yaml` + weights) and the FluidSynth SoundFont under `models/soundfonts/`. Gitignored. |
| `tools/fluidsynth/` | Optional Windows-only fallback: drop a portable FluidSynth build here and `midi_player.py` will pick `fluidsynth.exe` up via `tools/fluidsynth/**/bin/`. Avoids needing a system-wide install. |
| `.venv/` | Local Python 3.11 virtualenv created during setup. Gitignored. |

## How the pieces fit together

```
input/song.mp3
      |
      v  (run.py)
+--------------------+    +--------------------+    +--------------------+
| separate.py        | -> | audio_to_midi.py   | -> | midi_to_sheet.py   |
| -> piano stem .wav |    | -> .bytedance.mid  |    | -> .pdf + .musicxml|
+--------------------+    +--------------------+    +--------------------+
      |                          |                         |
      +--------------------------+-------------------------+
                                 v
              output/song_bs_roformer/  (piano.wav, .mid, .musicxml, .pdf)
```

`run.py` is the orchestrator; the three `src/` modules also work standalone via `python -m coltrane_to_sheet.<name>` when you want to iterate on a single stage.
