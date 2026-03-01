# Raga-Fusion Music Generator

Raga fusion app.

An educational tool that analyzes audio recordings of Indian classical music
to identify ragas, map Western notes to Hindustani svara notation, and explain
the musical theory behind each finding.

## Quick Start

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate          # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Make sure ffmpeg is installed (needed for MP3 files)
# macOS:    brew install ffmpeg
# Ubuntu:   sudo apt install ffmpeg
# Windows:  choco install ffmpeg

# 4. Run the analysis
python analyze_raga.py path/to/your_recording.mp3
```

### CLI Options

| Flag | Description |
|---|---|
| `--sa NOTE` | Override auto-detected tonic (Sa). Example: `--sa D` or `--sa "C#"` |
| `--verbose` / `-v` | Show additional technical details (semitone offsets, etc.) |

### Examples

```bash
# Auto-detect everything
python analyze_raga.py yaman_alaap.mp3

# Specify the tonic manually (if auto-detection is wrong)
python analyze_raga.py bhairavi_alaap.wav --sa C

# Verbose output
python analyze_raga.py recording.mp3 --verbose
```

## How to Analyze a Recording

### Supported Formats

MP3, WAV, FLAC, OGG, M4A. MP3 support requires ffmpeg installed on your system.

### What Makes a Good Recording?

- **Solo melodic instrument or voice** — sitar, sarangi, bansuri, vocal alaap
- **Minimal accompaniment** — tanpura drone is fine; heavy tabla can confuse pitch detection
- **Alaap section is ideal** — slow, deliberate exploration of the raga's notes
- **Clean audio** — less background noise means better pitch detection

### What the Tool Does

1. **Loads the audio** and resamples to 22050 Hz mono
2. **Detects pitches** using the pYIN algorithm (probabilistic monophonic pitch tracker)
3. **Identifies Sa** (the tonic) by finding the most frequently occurring pitch class
4. **Maps every detected pitch** to its Hindustani svara name relative to Sa
5. **Measures note durations** to identify the vadi (king note) and samvadi (queen note)
6. **Matches the scale** against all 10 Hindustani thaats
7. **Identifies the raga** from a database of 18 common ragas
8. **Maps to Western mode** for cross-cultural understanding

## How to Interpret Results

### Audio Overview

Shows recording length, how much of it contained pitched (melodic) audio,
and which note was detected as Sa.

### Note Distribution

A table showing every detected svara, how long it was held, and its percentage
of total pitched audio. The two most prominent notes are flagged:

- **VADI (King Note)** — The note held longest / most prominent. This is the
  emotional centre of the raga.
- **SAMVADI (Queen Note)** — Second most prominent. Usually a 4th or 5th
  from the vadi.

### Raga Identification

- **Confidence** — Higher is better. Above 60% is a strong match.
  Below 40% means the tool is uncertain (try `--sa` to correct the tonic).
- **Thaat** — The parent scale system (like Western modes but for Indian music).
  There are exactly 10 thaats in Hindustani music.
- **Why This Match** — Explains exactly which factors contributed to the match:
  thaat overlap, vadi/samvadi alignment, scale completeness.
- **About the Raga** — Educational paragraph with mood, performance time,
  characteristic phrases (pakad), and ascending/descending patterns.
- **Other Possible Ragas** — Runner-up candidates if the match isn't definitive.

### Western Equivalent

Shows the closest Western mode and builds the scale using Western note names.
Useful for musicians trained in Western theory who want to understand the
relationship between modes and thaats.

### Detected Scale

A visual representation of which of the 12 semitones are active in the
recording, shown in both svara and Western notation.

## Understanding Ragas (Quick Primer)

| Concept | Meaning |
|---|---|
| **Sa** | Tonic (home note). Every raga starts and ends here. |
| **Thaat** | Parent scale — 7 notes chosen from 12 semitones. There are 10 thaats. |
| **Raga** | A melodic framework derived from a thaat, with rules about emphasis and movement. |
| **Vadi** | King note — the most important note in the raga. |
| **Samvadi** | Queen note — second in importance, supports the vadi. |
| **Aroha** | Ascending scale pattern. |
| **Avaroha** | Descending scale pattern. |
| **Pakad** | A short characteristic phrase that makes the raga recognizable. |
| **Shuddh** | Natural / unaltered form of a note. |
| **Komal** | Flattened (lowered by one semitone). Notated with lowercase: r, g, d, n. |
| **Tivra** | Sharpened (raised by one semitone). Only applies to Ma → M'. |

## Next Steps

### Validate Against Known Recordings

Test the tool with recordings where you already know the raga:
- Download an alaap of Raga Yaman and verify it identifies Kalyan thaat with Ga as vadi
- Try Raga Bhairavi — it should detect Bhairavi thaat with all komal notes
- Try Raga Bhairav — check that it finds the distinctive komal Re + shuddh Ga combination

### Record Your Own Alaap

1. Set a tanpura drone (apps like iTanpura or Tanpura Droid work well)
2. Slowly explore the notes of a raga you're learning
3. Record 2–5 minutes of alaap (no fast taans or ornaments)
4. Run the analysis to see if the tool detects your intended raga
5. Compare your note durations — are you emphasizing the vadi enough?

### Phrase-Level Analysis (Future Work)

The current tool analyzes *aggregate* note durations. Future improvements could:
- Detect individual phrases and their svara sequences
- Compare phrases against known pakad patterns
- Analyze aroha/avaroha movement (does the melody follow the prescribed ascent/descent?)
- Detect gamakas (ornaments) and andolan (oscillations)
- Support Carnatic raga identification (melakarta system)

## Project Structure

```
Raga-Fusion Music Generator/
  analyze_raga.py       Main analysis tool
  requirements.txt      Python dependencies
  README.md             This file
```

## Requirements

- Python 3.10+
- ffmpeg (for MP3 support)
- See `requirements.txt` for Python packages
