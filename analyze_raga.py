#!/usr/bin/env python3
"""
analyze_raga.py — Educational Hindustani Raga Analysis Tool

Analyzes audio recordings of Indian classical music to identify ragas.
Extracts pitch information, maps Western notes to Hindustani svara notation,
detects the underlying thaat (parent scale) and raga, and produces an
educational report explaining each finding.

Usage:
    python analyze_raga.py recording.mp3
    python analyze_raga.py recording.wav --sa C4
    python analyze_raga.py recording.mp3 --verbose

Examples:
    # Analyze a Yaman alaap recording
    python analyze_raga.py yaman_alaap.mp3

    # Specify the tonic note (Sa) manually if auto-detection is wrong
    python analyze_raga.py recording.wav --sa D

    # Get additional technical details
    python analyze_raga.py recording.mp3 --verbose

Requires:
    pip install -r requirements.txt
    (librosa, numpy, soundfile; ffmpeg for MP3 support)
"""

import argparse
import sys
import textwrap
from pathlib import Path
from collections import Counter
from dataclasses import dataclass

import numpy as np

try:
    import librosa
except ImportError:
    print("\n  ERROR: librosa is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)

try:
    import soundfile as _sf  # noqa: F401 — librosa backend
except ImportError:
    print("\n  ERROR: soundfile is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

SAMPLE_RATE = 22050
HOP_LENGTH = 512
FRAME_DURATION = HOP_LENGTH / SAMPLE_RATE  # ~23 ms per frame

SUPPORTED_FORMATS = ('.mp3', '.wav', '.flac', '.ogg', '.m4a')

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Semitone offset from Sa  →  abbreviated svara symbol
DEGREE_TO_SVARA = {
    0: 'S', 1: 'r', 2: 'R', 3: 'g', 4: 'G',
    5: 'm', 6: 'M', 7: 'P', 8: 'd', 9: 'D',
    10: 'n', 11: 'N',
}

# Semitone offset → (abbreviation, full name, one-line explanation)
DEGREE_INFO = {
    0:  ('Sa',  'Shadja',          'The tonic — home base of the raga. Always present.'),
    1:  ('re',  'Komal Rishabh',   'Flattened 2nd. Creates distinctive tension near Sa.'),
    2:  ('Re',  'Shuddh Rishabh',  'Natural 2nd degree.'),
    3:  ('ga',  'Komal Gandhar',   'Flattened 3rd. Gives a "minor" feeling.'),
    4:  ('Ga',  'Shuddh Gandhar',  'Natural 3rd. Gives a "major" feeling.'),
    5:  ('ma',  'Shuddh Madhyam',  'Natural 4th degree.'),
    6:  ('Ma',  'Tivra Madhyam',   'Raised 4th — hallmark of Kalyan thaat.'),
    7:  ('Pa',  'Pancham',         'Perfect 5th. Most consonant note after Sa.'),
    8:  ('dha', 'Komal Dhaivat',   'Flattened 6th degree.'),
    9:  ('Dha', 'Shuddh Dhaivat',  'Natural 6th degree.'),
    10: ('ni',  'Komal Nishad',    'Flattened 7th degree.'),
    11: ('Ni',  'Shuddh Nishad',   'Natural 7th degree.'),
}

THAAT_TO_WESTERN = {
    'bilaval':  ('Ionian (Major)',           'Identical to the Western major scale'),
    'kalyan':   ('Lydian',                   'Major scale with raised 4th degree (#4)'),
    'khamaj':   ('Mixolydian',               'Major scale with lowered 7th degree (b7)'),
    'kafi':     ('Dorian',                   'Minor scale with raised 6th degree'),
    'asavari':  ('Aeolian (Natural Minor)',   'The Western natural minor scale'),
    'bhairavi': ('Phrygian',                 'Minor scale with lowered 2nd degree (b2)'),
    'bhairav':  ('Double Harmonic Major',    'Uses b2 and b6 with natural 3rd and 7th'),
    'todi':     ('Phrygian #4',              'Like Phrygian but with a raised 4th'),
    'marwa':    ('Lydian b2',                'Like Lydian but with a lowered 2nd'),
    'purvi':    ('Lydian b2 b6',             'Lydian with lowered 2nd and 6th'),
}

MIN_NOTE_PRESENCE_PCT = 2.0   # "confidently present" for scale identification
THAAT_PRESENCE_PCT = 0.5      # lower bar for thaat matching (catch lightly-used notes)

# Sa and Pa are structurally fixed in every raga — they cannot be vadi/samvadi
FIXED_DEGREES = {0, 7}  # Sa=0, Pa=7


# ═══════════════════════════════════════════════════════════════════════
#  RAGA DATABASE
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RagaInfo:
    """A single raga's musical identity.

    Attributes:
        name:      Raga name, e.g. "Yaman".
        thaat:     Parent thaat (lowercase), e.g. "kalyan".
        aroha:     Ascending scale notation.
        avaroha:   Descending scale notation.
        vadi:      Scale degree (0-11 semitones from Sa) of the king note.
        samvadi:   Scale degree of the queen note.
        time:      Traditional performance time window.
        mood:      Emotional character keywords.
        description: Educational paragraph about the raga.
        degrees:   Tuple of all scale degrees used in the raga.
        pakad:     Characteristic catch-phrase of the raga.

    Example:
        >>> yaman = RagaInfo(
        ...     name="Yaman", thaat="kalyan",
        ...     aroha="N R G M' P D N S'", avaroha="S' N D P M' G R S",
        ...     vadi=4, samvadi=11,
        ...     time="Early night", mood="Serene",
        ...     description="...", degrees=(0,2,4,6,7,9,11),
        ... )
        >>> DEGREE_TO_SVARA[yaman.vadi]
        'G'
    """
    name: str
    thaat: str
    aroha: str
    avaroha: str
    vadi: int
    samvadi: int
    time: str
    mood: str
    description: str
    degrees: tuple
    pakad: str = ""


def _build_raga_database():
    """Return a list of 18 well-known Hindustani ragas spanning all 10 thaats.

    Includes heptatonic, hexatonic, and pentatonic varieties so the matcher
    can handle a wide range of recordings.

    Returns:
        list[RagaInfo]
    """
    return [
        # ── Kalyan thaat ──────────────────────────────────────────────
        RagaInfo(
            name="Yaman", thaat="kalyan",
            aroha="N R G M' P D N S'",
            avaroha="S' N D P M' G R S",
            vadi=4, samvadi=11,
            time="Early night (6–9 PM)",
            mood="Serene, devotional, romantic",
            description=(
                "One of the most fundamental ragas in Hindustani music. "
                "The raised Ma (tivra Ma / F# when Sa=C) gives it a "
                "distinctive brightness compared to its parent Bilaval. "
                "Often the first serious raga taught to students. "
                "Creates a mood of devotion and quiet joy."
            ),
            degrees=(0, 2, 4, 6, 7, 9, 11),
            pakad="N R G, R G M' P, G M' D N",
        ),
        RagaInfo(
            name="Bhupali", thaat="kalyan",
            aroha="S R G P D S'",
            avaroha="S' D P G R S",
            vadi=4, samvadi=9,
            time="First prahar of night (6–9 PM)",
            mood="Calm, devotional, peaceful",
            description=(
                "A pentatonic (audav) raga using only 5 notes — Ma and Ni "
                "are completely absent. Its simplicity gives it a pure, "
                "devotional quality. Shares notes with Raga Deshkar but "
                "differs in emphasis and movement."
            ),
            degrees=(0, 2, 4, 7, 9),
            pakad="G R, G P, D P G",
        ),

        # ── Bilaval thaat ─────────────────────────────────────────────
        RagaInfo(
            name="Bilaval", thaat="bilaval",
            aroha="S R G m P D N S'",
            avaroha="S' N D P m G R S",
            vadi=9, samvadi=4,
            time="Late morning (9 AM – 12 PM)",
            mood="Bright, joyful, optimistic",
            description=(
                "Equivalent to the Western major scale — all shuddh "
                "(natural) notes. A morning raga conveying brightness and "
                "optimism. Its simplicity makes it a good introduction to "
                "raga structure for Western-trained musicians."
            ),
            degrees=(0, 2, 4, 5, 7, 9, 11),
            pakad="G R G, P G m P, D P G",
        ),
        RagaInfo(
            name="Durga", thaat="bilaval",
            aroha="S R m P D S'",
            avaroha="S' D P m R S",
            vadi=7, samvadi=2,
            time="Late evening",
            mood="Peaceful, devotional, calm",
            description=(
                "A serene pentatonic raga omitting Ga and Ni entirely. "
                "Uses only shuddh (natural) notes. Often performed in "
                "devotional and meditative contexts. Simple yet deeply "
                "moving."
            ),
            degrees=(0, 2, 5, 7, 9),
            pakad="m R S, m P D, P m R S",
        ),
        RagaInfo(
            name="Hamsadhwani", thaat="bilaval",
            aroha="S R G P N S'",
            avaroha="S' N P G R S",
            vadi=4, samvadi=11,
            time="Any time (auspicious occasions)",
            mood="Joyful, auspicious, bright",
            description=(
                "A joyful pentatonic raga from the Carnatic tradition, now "
                "popular in Hindustani music too. Omits Ma and Dha. Often "
                "performed to open concerts or mark auspicious occasions."
            ),
            degrees=(0, 2, 4, 7, 11),
            pakad="G R S, R G P, N P G",
        ),

        # ── Khamaj thaat ──────────────────────────────────────────────
        RagaInfo(
            name="Khamaj", thaat="khamaj",
            aroha="S G m P D n S'",
            avaroha="S' N D P m G R S",
            vadi=4, samvadi=10,
            time="Late night (9 PM – midnight)",
            mood="Romantic, light, playful",
            description=(
                "A romantic raga using komal Ni in ascent but shuddh Ni "
                "in descent. Popular in thumri and light classical forms. "
                "Expresses shringara rasa (romantic sentiment)."
            ),
            degrees=(0, 2, 4, 5, 7, 9, 10, 11),
            pakad="S G m P, D n D P, G m G R S",
        ),
        RagaInfo(
            name="Des", thaat="khamaj",
            aroha="S R m P n S'",
            avaroha="S' n D P m G R S",
            vadi=2, samvadi=7,
            time="Late night (9 PM – midnight)",
            mood="Romantic, festive, playful",
            description=(
                "A popular raga in light classical and film music. Ga is "
                "omitted in ascent but present in descent. Has a romantic, "
                "festive character beloved in North Indian culture."
            ),
            degrees=(0, 2, 4, 5, 7, 9, 10),
            pakad="R m P, n D P, m G R S",
        ),

        # ── Kafi thaat ────────────────────────────────────────────────
        RagaInfo(
            name="Kafi", thaat="kafi",
            aroha="S R g m P D n S'",
            avaroha="S' n D P m g R S",
            vadi=7, samvadi=2,
            time="Late night",
            mood="Romantic, pathos, devotional",
            description=(
                "Uses komal Ga and komal Ni, lending a tender, emotional "
                "quality. Equivalent to the Western Dorian mode. Popular "
                "in semi-classical thumri and dadra compositions."
            ),
            degrees=(0, 2, 3, 5, 7, 9, 10),
            pakad="m g R S, P g m P, D n D P",
        ),
        RagaInfo(
            name="Bhimpalasi", thaat="kafi",
            aroha="S g m P n S'",
            avaroha="S' n D P m g R S",
            vadi=5, samvadi=0,
            time="Afternoon (3–6 PM)",
            mood="Romantic, longing, yearning",
            description=(
                "An afternoon raga of romantic longing. Re is omitted in "
                "ascent. Known for slow, meditative alaap that builds "
                "emotional intensity gradually."
            ),
            degrees=(0, 2, 3, 5, 7, 9, 10),
            pakad="g m P, n P, D P m g R S",
        ),
        RagaInfo(
            name="Bageshree", thaat="kafi",
            aroha="S g m D n S'",
            avaroha="S' n D m g R S",
            vadi=5, samvadi=0,
            time="Second prahar of night (9 PM – midnight)",
            mood="Romantic, yearning, serene",
            description=(
                "A beautiful night raga of romantic longing. Pa is entirely "
                "omitted. Uses komal Ga and komal Ni. Known for its gentle, "
                "yearning character."
            ),
            degrees=(0, 2, 3, 5, 9, 10),
            pakad="m g R S, g m D, n D m g R S",
        ),

        # ── Asavari thaat ─────────────────────────────────────────────
        RagaInfo(
            name="Asavari", thaat="asavari",
            aroha="S R m P d S'",
            avaroha="S' d n d P m g R S",
            vadi=8, samvadi=3,
            time="Late morning",
            mood="Pathos, devotion, seriousness",
            description=(
                "Uses komal Ga, Dha, and Ni. Equivalent to the Western "
                "natural minor (Aeolian) mode. Ga and Ni are omitted in "
                "ascent, creating a distinctive ascending pattern."
            ),
            degrees=(0, 2, 3, 5, 7, 8, 10),
            pakad="d m P, d n d P, m g R S",
        ),
        RagaInfo(
            name="Darbari Kanada", thaat="asavari",
            aroha="S R g m P d n S'",
            avaroha="S' d n P m g R S",
            vadi=2, samvadi=7,
            time="Late night (midnight – 3 AM)",
            mood="Majestic, serious, contemplative",
            description=(
                "One of the grandest ragas, associated with the Mughal court "
                "of Tansen. Characterized by a slow oscillation (andolan) on "
                "komal Ga and komal Dha. Demands patient, meditative treatment."
            ),
            degrees=(0, 2, 3, 5, 7, 8, 10),
            pakad="R g, m P d, n P, d m g, m R S",
        ),

        # ── Bhairavi thaat ────────────────────────────────────────────
        RagaInfo(
            name="Bhairavi", thaat="bhairavi",
            aroha="S r g m P d n S'",
            avaroha="S' n d P m g r S",
            vadi=5, samvadi=0,
            time="Early morning (or any time as concluding raga)",
            mood="Devotional, compassion, tranquility",
            description=(
                "Called the 'Queen of Ragas.' Uses all komal (flat) notes "
                "except Ma and Pa. The most complete expression of devotion "
                "and compassion. Often the final raga of a concert."
            ),
            degrees=(0, 1, 3, 5, 7, 8, 10),
            pakad="g m d P, g m r S, m g r S",
        ),
        RagaInfo(
            name="Malkauns", thaat="bhairavi",
            aroha="S g m d n S'",
            avaroha="S' n d m g S",
            vadi=5, samvadi=0,
            time="Late night (midnight – 3 AM)",
            mood="Serious, meditative, mystical",
            description=(
                "A powerful pentatonic raga. Re, Ga, and Dha are komal; "
                "Pa is omitted entirely. Creates a deep, mystical atmosphere "
                "ideal for late-night meditation and introspection."
            ),
            degrees=(0, 3, 5, 8, 10),
            pakad="m g S, d n d, m g, m d n S'",
        ),

        # ── Bhairav thaat ─────────────────────────────────────────────
        RagaInfo(
            name="Bhairav", thaat="bhairav",
            aroha="S r G m P d N S'",
            avaroha="S' N d P m G r S",
            vadi=8, samvadi=1,
            time="Early morning (sunrise)",
            mood="Serious, devotional, grandeur",
            description=(
                "A morning raga of great majesty. The contrast of komal Re "
                "with shuddh Ga, and komal Dha with shuddh Ni, creates a "
                "unique tension. Associated with Lord Shiva and sunrise."
            ),
            degrees=(0, 1, 4, 5, 7, 8, 11),
            pakad="r G m, d N S', N d P, m G r S",
        ),

        # ── Todi thaat ────────────────────────────────────────────────
        RagaInfo(
            name="Todi", thaat="todi",
            aroha="S r g M' d N S'",
            avaroha="S' N d P M' g r S",
            vadi=8, samvadi=3,
            time="Late morning (9 AM – 12 PM)",
            mood="Serious, intense, contemplative",
            description=(
                "A powerful raga using three komal notes (Re, Ga, Dha) with "
                "tivra Ma. Pa is often omitted in ascent. One of the most "
                "challenging and rewarding ragas to perform."
            ),
            degrees=(0, 1, 3, 6, 7, 8, 11),
            pakad="r g M' g, d N d, M' g r S",
        ),

        # ── Marwa thaat ───────────────────────────────────────────────
        RagaInfo(
            name="Marwa", thaat="marwa",
            aroha="S r G M' D N S'",
            avaroha="S' N D M' G r S",
            vadi=9, samvadi=1,
            time="Dusk (evening twilight)",
            mood="Serious, restless, intense",
            description=(
                "A powerful twilight raga that avoids Pa (the 5th) entirely. "
                "The combination of komal Re with tivra Ma creates a restless "
                "tension. Resolution to Sa always feels uncertain."
            ),
            degrees=(0, 1, 4, 6, 9, 11),
            pakad="r G M' D, N D N r' S', N D M' G r S",
        ),

        # ── Purvi thaat ───────────────────────────────────────────────
        RagaInfo(
            name="Purvi", thaat="purvi",
            aroha="S r G M' P d N S'",
            avaroha="S' N d P M' G r S",
            vadi=4, samvadi=11,
            time="Evening twilight",
            mood="Serious, contemplative, mystical",
            description=(
                "An evening raga with a mystical character. Uses komal Re, "
                "tivra Ma, and komal Dha. The interplay of these altered "
                "notes creates deep contemplation."
            ),
            degrees=(0, 1, 4, 6, 7, 8, 11),
            pakad="r G M' P, d N d P, M' G r S",
        ),
    ]


RAGA_DB = _build_raga_database()


# ═══════════════════════════════════════════════════════════════════════
#  CORE ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def load_audio(filepath):
    """Load an audio file and return the waveform with metadata.

    Supports MP3, WAV, FLAC, OGG, and M4A.  MP3 requires ffmpeg.

    Args:
        filepath: Path to the audio file.

    Returns:
        tuple: (y, sr, duration_seconds)

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is unsupported.
        RuntimeError: If loading fails (e.g. missing ffmpeg for MP3).

    Example:
        >>> y, sr, dur = load_audio("yaman_alaap.mp3")
        >>> print(f"Loaded {dur:.1f}s at {sr} Hz")
        Loaded 247.3s at 22050 Hz
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {filepath}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )

    try:
        y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    except Exception as e:
        if suffix == '.mp3':
            raise RuntimeError(
                f"Failed to load MP3. Ensure ffmpeg is installed:\n"
                f"  macOS:   brew install ffmpeg\n"
                f"  Ubuntu:  sudo apt install ffmpeg\n"
                f"  Windows: choco install ffmpeg\n"
                f"  Error:   {e}"
            ) from e
        raise

    duration = librosa.get_duration(y=y, sr=sr)
    return y, sr, duration


def detect_pitches(y, sr):
    """Extract pitched frames from audio using the pYIN algorithm.

    pYIN is a probabilistic variant of YIN, well-suited for monophonic
    vocal or instrumental recordings like alaap.

    Args:
        y:  Audio time-series (numpy array).
        sr: Sample rate in Hz.

    Returns:
        tuple: (times, frequencies, midi_notes, pitch_classes)
            - times:         Timestamps in seconds for each voiced frame.
            - frequencies:   Fundamental frequency (Hz) per voiced frame.
            - midi_notes:    Rounded MIDI note numbers.
            - pitch_classes: Pitch classes 0-11 (0 = C, 1 = C#, …).

    Raises:
        ValueError: If no pitched content is found.

    Example:
        >>> times, freqs, midi, pcs = detect_pitches(y, sr)
        >>> print(f"{len(times)} voiced frames detected")
    """
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y,
        fmin=librosa.note_to_hz('C2'),
        fmax=librosa.note_to_hz('C6'),
        sr=sr,
        hop_length=HOP_LENGTH,
    )

    valid = ~np.isnan(f0) & voiced_flag
    if not np.any(valid):
        raise ValueError(
            "No pitched content detected in this recording.\n"
            "Possible causes:\n"
            "  - The recording is percussion-only (tabla, pakhawaj)\n"
            "  - Audio is too noisy or distorted\n"
            "  - File is silent or nearly silent"
        )

    indices = np.where(valid)[0]
    times = librosa.frames_to_time(indices, sr=sr, hop_length=HOP_LENGTH)
    frequencies = f0[valid]
    midi_notes = np.round(librosa.hz_to_midi(frequencies)).astype(int)
    pitch_classes = midi_notes % 12

    return times, frequencies, midi_notes, pitch_classes


def detect_sa(pitch_classes, sa_override=None):
    """Detect the tonic note (Sa) from pitch statistics.

    By default, selects the most frequently occurring pitch class —
    a reasonable heuristic for alaap recordings where Sa is heavily
    emphasised.  Use ``--sa`` to override if auto-detection is wrong.

    Args:
        pitch_classes: Array of pitch classes (0-11).
        sa_override:   Optional note name (e.g. 'C', 'D#', 'Bb4').

    Returns:
        tuple: (sa_pitch_class, sa_note_name, sa_hz)

    Example:
        >>> sa_pc, sa_note, sa_hz = detect_sa(pitch_classes, sa_override='D')
        >>> print(f"Sa = {sa_note} ({sa_hz:.1f} Hz)")
        Sa = D (293.7 Hz)
    """
    if sa_override:
        note = sa_override.strip()
        has_octave = any(ch.isdigit() for ch in note)
        midi = librosa.note_to_midi(note if has_octave else note + '4')
        sa_pc = int(midi % 12)
    else:
        counter = Counter(int(pc) for pc in pitch_classes)
        sa_pc = counter.most_common(1)[0][0]

    sa_note = NOTE_NAMES[sa_pc]
    sa_hz = float(librosa.midi_to_hz(60 + sa_pc))
    return sa_pc, sa_note, sa_hz


def analyze_note_distribution(pitch_classes, midi_notes, times, sa_pc):
    """Compute how long each scale degree is held and its percentage.

    Args:
        pitch_classes: Array of pitch classes (0-11).
        midi_notes:    Array of MIDI note numbers (for octave display).
        times:         Frame timestamps in seconds.
        sa_pc:         Pitch class of Sa (0-11).

    Returns:
        list[dict]: Entries sorted from most to least prominent, each with
        keys: degree, svara_abbr, svara_full, svara_desc, note_name,
        duration_sec, percentage.

    Example:
        >>> dist = analyze_note_distribution(pcs, midi, t, sa_pc)
        >>> for d in dist[:3]:
        ...     print(f"{d['svara_abbr']:>3}  {d['percentage']:5.1f}%")
          G   18.7%
          N   13.2%
          M    11.0%
    """
    degrees = (pitch_classes.astype(int) - sa_pc) % 12

    degree_duration = Counter()
    degree_note_counter = {}

    for i, deg in enumerate(degrees):
        deg = int(deg)
        degree_duration[deg] += FRAME_DURATION
        if deg not in degree_note_counter:
            degree_note_counter[deg] = Counter()
        degree_note_counter[deg][int(midi_notes[i])] += 1

    total = sum(degree_duration.values())
    if total == 0:
        return []

    distribution = []
    for deg in sorted(degree_duration):
        dur = degree_duration[deg]
        pct = (dur / total) * 100
        most_common_midi = degree_note_counter[deg].most_common(1)[0][0]
        note_name = librosa.midi_to_note(most_common_midi)
        abbr, full, desc = DEGREE_INFO[deg]
        distribution.append({
            'degree': deg,
            'svara_abbr': abbr,
            'svara_full': full,
            'svara_desc': desc,
            'note_name': note_name,
            'duration_sec': dur,
            'percentage': pct,
        })

    distribution.sort(key=lambda x: x['duration_sec'], reverse=True)
    return distribution


def identify_thaat(distribution):
    """Score every Hindustani thaat against the detected note distribution.

    Uses a weighted combination of *coverage* (how many of the recording's
    notes fall inside the thaat) and *completeness* (how many thaat notes
    appear in the recording), with a penalty for extra notes outside the
    thaat.

    Args:
        distribution: Note distribution from ``analyze_note_distribution``.

    Returns:
        list[tuple]: ``(thaat_name, score, thaat_degrees, explanation)``
        sorted best-first.

    Example:
        >>> matches = identify_thaat(dist)
        >>> print(matches[0][0], f"{matches[0][1]:.0%}")
        kalyan 92%
    """
    # Two tiers: strong notes shape the score, weak notes help disambiguate thaats
    strong = {d['degree'] for d in distribution
              if d['percentage'] >= MIN_NOTE_PRESENCE_PCT}
    weak = {d['degree'] for d in distribution
            if THAAT_PRESENCE_PCT <= d['percentage'] < MIN_NOTE_PRESENCE_PCT}
    present = strong | weak
    present.add(0)

    results = []
    for thaat in librosa.list_thaat():
        thaat_deg = set(librosa.thaat_to_degrees(thaat))

        strong_in = len(strong & thaat_deg)
        weak_in = len(weak & thaat_deg)
        total_in = strong_in + weak_in * 0.5  # weak notes count at half weight

        coverage = total_in / (len(strong) + len(weak) * 0.5) if present else 0
        completeness = total_in / len(thaat_deg)
        extra = present - thaat_deg
        extra_penalty = len(extra & strong) * 0.10 + len(extra & weak) * 0.03

        score = max(0.0, min(1.0, coverage * 0.60 + completeness * 0.40 - extra_penalty))

        parts = []
        if extra:
            parts.append("Extra notes: " + ", ".join(DEGREE_TO_SVARA[d] for d in sorted(extra)))
        missing = thaat_deg - present
        if missing:
            parts.append("Missing: " + ", ".join(DEGREE_TO_SVARA[d] for d in sorted(missing)))

        results.append((thaat, score, tuple(sorted(thaat_deg)), "; ".join(parts)))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def identify_raga(thaat_matches, distribution):
    """Identify the most likely raga by cross-referencing thaat, vadi, and samvadi.

    Scoring weights:
        30 % — thaat match score
        40 % — scale-degree overlap (with percentage-weighted penalty for
               strongly-present notes that contradict the raga's scale)
        18 % — vadi (king note) alignment
        12 % — samvadi (queen note) alignment

    Args:
        thaat_matches: Ranked thaat results from ``identify_thaat``.
        distribution:  Note distribution list.

    Returns:
        list[tuple]: ``(RagaInfo, confidence_0_to_1, [reason_strings])``
        sorted best-first.

    Example:
        >>> ragas = identify_raga(thaats, dist)
        >>> best = ragas[0]
        >>> print(f"Raga {best[0].name}  confidence={best[1]:.0%}")
        Raga Yaman  confidence=87%
    """
    if not distribution:
        return []

    # Sa and Pa are structurally fixed — vadi/samvadi must be other svaras
    melodic = [d for d in distribution if d['degree'] not in FIXED_DEGREES]
    detected_vadi = melodic[0]['degree'] if melodic else distribution[0]['degree']
    detected_samvadi = melodic[1]['degree'] if len(melodic) > 1 else None

    # Use the lower threshold for raga matching so weakly-present notes
    # (like tivra Ma at < 2 %) still count when they fall inside a raga's scale
    present = {d['degree'] for d in distribution
               if d['percentage'] >= THAAT_PRESENCE_PCT}
    present.add(0)

    thaat_score_map = {name: sc for name, sc, _, _ in thaat_matches}

    # Build a lookup: degree → percentage for penalty computation
    deg_pct = {d['degree']: d['percentage'] for d in distribution}

    candidates = []
    for raga in RAGA_DB:
        reasons = []
        score = 0.0

        # --- Thaat component (30 %) ---
        t_score = thaat_score_map.get(raga.thaat, 0.0)
        score += t_score * 0.30
        reasons.append(f"Thaat match ({raga.thaat.title()}): {t_score:.0%}")

        # --- Scale overlap (40 %) — two-way: how well the raga explains the
        #     recording AND how much of the raga is detected ---
        raga_deg = set(raga.degrees)
        if raga_deg:
            explained = len(present & raga_deg) / len(present) if present else 0
            detected = len(present & raga_deg) / len(raga_deg)
            overlap = (explained + detected) / 2.0
            extra_degrees = present - raga_deg
            extra_pct = sum(deg_pct.get(d, 0) for d in extra_degrees) / 100.0
            adj = max(0.0, overlap - extra_pct)
            score += adj * 0.40
            if extra_degrees:
                extra_names = ", ".join(
                    f"{DEGREE_TO_SVARA[d]}({deg_pct.get(d,0):.1f}%)"
                    for d in sorted(extra_degrees)
                )
                reasons.append(f"Scale fit: {adj:.0%} (extra notes: {extra_names})")
            else:
                reasons.append(f"Scale fit: {adj:.0%} (all detected notes match)")

        # --- Vadi (18 %) ---
        if detected_vadi == raga.vadi:
            score += 0.18
            reasons.append(
                f"Vadi match: {DEGREE_TO_SVARA[raga.vadi]} is the most prominent melodic note "
                f"— matches {raga.name}'s king note"
            )
        elif detected_samvadi == raga.vadi:
            score += 0.08
            reasons.append(
                f"Vadi partial: {DEGREE_TO_SVARA[raga.vadi]} is the 2nd most prominent melodic note"
            )

        # --- Samvadi (12 %) ---
        if detected_samvadi is not None and detected_samvadi == raga.samvadi:
            score += 0.12
            reasons.append(
                f"Samvadi match: {DEGREE_TO_SVARA[raga.samvadi]} is the 2nd most prominent "
                f"— matches {raga.name}'s queen note"
            )
        elif detected_vadi == raga.samvadi:
            score += 0.05
            reasons.append(
                f"Samvadi partial: {DEGREE_TO_SVARA[raga.samvadi]} is most prominent melodic note"
            )

        score = max(0.0, min(1.0, score))
        candidates.append((raga, score, reasons))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def detect_western_mode(best_thaat, sa_note):
    """Map the best-matching thaat to its nearest Western mode equivalent.

    Args:
        best_thaat: Thaat name string (e.g. "kalyan").
        sa_note:    Note name of Sa (e.g. "C", "D#").

    Returns:
        dict with keys: mode_name, description, scale_notes, key.

    Example:
        >>> m = detect_western_mode("kalyan", "C")
        >>> print(m['key'], "—", m['scale_notes'])
        C Lydian — C D E F♯ G A B
    """
    mode_name, mode_desc = THAAT_TO_WESTERN.get(
        best_thaat, ('Unknown', 'No standard Western equivalent')
    )

    sa_midi = librosa.note_to_midi(sa_note + '4')
    thaat_degrees = librosa.thaat_to_degrees(best_thaat)
    scale_notes = []
    for deg in thaat_degrees:
        note = librosa.midi_to_note(sa_midi + deg, octave=False)
        scale_notes.append(note)

    return {
        'mode_name': mode_name,
        'description': mode_desc,
        'scale_notes': '  '.join(scale_notes),
        'key': f"{sa_note} {mode_name}",
    }


# ═══════════════════════════════════════════════════════════════════════
#  EDUCATIONAL REPORT
# ═══════════════════════════════════════════════════════════════════════

REPORT_WIDTH = 64


def _bar(char='═'):
    return char * REPORT_WIDTH


def _section(title):
    return f"\n  --- {title} ---"


def _wrap_text(text, indent=4, width=None):
    width = width or (REPORT_WIDTH - 2)
    return textwrap.fill(
        text, width=width,
        initial_indent=' ' * indent,
        subsequent_indent=' ' * indent,
    )


def print_report(filepath, duration, sa_info, distribution,
                 thaat_matches, raga_matches, western_mode, verbose=False):
    """Print a richly formatted, educational analysis report.

    Designed to teach the reader about raga structure while presenting
    the analysis results.  Every musical term is explained on first use.

    Args:
        filepath:      Path to the analyzed file.
        duration:       Audio duration in seconds.
        sa_info:       ``(sa_pitch_class, sa_note_name, sa_hz)``.
        distribution:  Sorted note distribution list.
        thaat_matches: Ranked thaat match list.
        raga_matches:  Ranked raga match list.
        western_mode:  Western mode dict.
        verbose:       Show extra technical details.

    Example:
        >>> print_report("alaap.mp3", 120.0, (0,"C",261.6), dist,
        ...              thaats, ragas, mode)
    """
    sa_pc, sa_note, sa_hz = sa_info
    filename = Path(filepath).name

    # ── Header ────────────────────────────────────────────────────
    print(f"\n{_bar()}")
    print(f"  RAGA ANALYSIS REPORT")
    print(f"  File: {filename}")
    print(_bar())

    # ── Audio Overview ────────────────────────────────────────────
    print(_section("AUDIO OVERVIEW"))
    mins, secs = divmod(duration, 60)
    pitched_dur = sum(d['duration_sec'] for d in distribution)
    pitched_pct = (pitched_dur / duration * 100) if duration > 0 else 0
    print(f"    Duration:       {int(mins)}m {secs:.1f}s ({duration:.1f}s)")
    print(f"    Sample Rate:    {SAMPLE_RATE} Hz")
    print(f"    Detected Sa:    {sa_note}4 ({sa_hz:.1f} Hz)")
    print(f"    Pitched Audio:  {pitched_dur:.1f}s ({pitched_pct:.0f}% of recording)")

    # ── Note Distribution Table ───────────────────────────────────
    print(_section("NOTE DISTRIBUTION"))
    print()
    hdr = f"    {'Note':<8} {'Svara':<6} {'Duration':>9} {'%':>7}   Role"
    print(hdr)
    print(f"    {'─'*8} {'─'*6} {'─'*9} {'─'*7}   {'─'*18}")

    # Sa and Pa are structurally fixed — vadi/samvadi are the other prominent notes
    melodic = [d for d in distribution if d['degree'] not in FIXED_DEGREES]
    vadi_entry = melodic[0] if melodic else None
    samvadi_entry = melodic[1] if len(melodic) > 1 else None

    for entry in distribution:
        deg = entry['degree']
        if deg == 0:
            role = "(Sa — TONIC)"
        elif deg == 7:
            role = "(Pa — FIFTH)"
        elif vadi_entry and deg == vadi_entry['degree']:
            role = "* VADI (King)"
        elif samvadi_entry and deg == samvadi_entry['degree']:
            role = "* SAMVADI (Queen)"
        else:
            role = ""
        print(
            f"    {entry['note_name']:<8} "
            f"{entry['svara_abbr']:<6} "
            f"{entry['duration_sec']:>8.1f}s "
            f"{entry['percentage']:>6.1f}%   "
            f"{role}"
        )

    # ── Vadi / Samvadi educational callouts ───────────────────────
    if vadi_entry:
        v = vadi_entry
        print()
        print(f"    -> Found note {v['note_name']} held for "
              f"{v['duration_sec']:.1f} seconds ({v['percentage']:.1f}% of pitched audio)")
        print(f"       This is likely the VADI (king note) of this raga")
        print(f"       In Indian notation: {v['svara_abbr']} ({v['svara_full']})")
        print(f"       {v['svara_desc']}")

    if samvadi_entry:
        s = samvadi_entry
        print()
        print(f"    -> Second most prominent: {s['note_name']} "
              f"({s['duration_sec']:.1f}s, {s['percentage']:.1f}%)")
        print(f"       Likely SAMVADI (queen note): "
              f"{s['svara_abbr']} ({s['svara_full']})")

    # ── What is Vadi / Samvadi? ───────────────────────────────────
    print(_section("WHAT IS VADI / SAMVADI?"))
    print()
    print(_wrap_text(
        "VADI (King Note): The most important note in a raga. "
        "The melody gravitates toward it, resting on it longest. "
        "Think of it as the emotional centre — the note that gives "
        "the raga its distinctive personality."
    ))
    print()
    print(_wrap_text(
        "SAMVADI (Queen Note): The second most important note, "
        "usually a perfect 4th or 5th from the vadi. It supports "
        "the vadi and helps distinguish ragas that share the same "
        "thaat (parent scale)."
    ))

    # ── Raga Identification ───────────────────────────────────────
    print(_section("RAGA IDENTIFICATION"))

    if raga_matches:
        best_raga, best_conf, best_reasons = raga_matches[0]
        print()
        print(f"    Best Match:     Raga {best_raga.name.upper()} "
              f"(Confidence: {best_conf:.0%})")
        print(f"    Thaat:          {best_raga.thaat.title()}")
        print(f"    Western Mode:   {western_mode['mode_name']}")

        print()
        print(f"    WHY THIS MATCH:")
        for reason in best_reasons:
            print(f"      * {reason}")

        print()
        print(f"    ABOUT RAGA {best_raga.name.upper()}:")
        print(_wrap_text(best_raga.description, indent=6))
        print()
        print(f"      Mood:      {best_raga.mood}")
        print(f"      Time:      {best_raga.time}")
        print(f"      Aroha:     {best_raga.aroha}")
        print(f"      Avaroha:   {best_raga.avaroha}")
        if best_raga.pakad:
            print(f"      Pakad:     {best_raga.pakad}")

        runners = [(r, c) for r, c, _ in raga_matches[1:4] if c > 0.15]
        if runners:
            print()
            print(f"    OTHER POSSIBLE RAGAS:")
            for raga, conf in runners:
                print(f"      - Raga {raga.name:<20} "
                      f"({conf:.0%}) [{raga.thaat.title()} thaat]")
    else:
        print("\n    Could not identify a matching raga.")

    # ── Western Equivalent ────────────────────────────────────────
    print(_section("WESTERN EQUIVALENT"))
    print()
    print(f"    Mode:    {western_mode['key']}")
    print(f"    Scale:   {western_mode['scale_notes']}")
    print()
    print(_wrap_text(western_mode['description'] + "."))

    if thaat_matches and thaat_matches[0][0] in ('bhairav', 'todi', 'marwa', 'purvi'):
        print()
        print(_wrap_text(
            f"Note: {thaat_matches[0][0].title()} thaat does not map to a "
            f"standard Western church mode. The label above is an "
            f"approximation — the raga system is richer than Western modes."
        ))

    # ── Scale Visualization ───────────────────────────────────────
    print(_section("DETECTED SCALE"))
    print()
    present = {d['degree'] for d in distribution
               if d['percentage'] >= MIN_NOTE_PRESENCE_PCT}
    top = "    "
    bot = "    "
    for deg in range(12):
        if deg in present:
            sv = DEGREE_TO_SVARA[deg]
            top += f" [{sv:>2}]"
            bot += f"  {NOTE_NAMES[(sa_pc + deg) % 12]:>2} "
        else:
            top += "  .  "
            bot += "     "
    print(top + "     (svara)")
    print(bot + "     (Western note)")

    if verbose:
        deg_line = "    "
        for deg in range(12):
            if deg in present:
                deg_line += f"  {deg:>2} "
            else:
                deg_line += "     "
        print(deg_line + "     (semitones from Sa)")

    # ── Footer ────────────────────────────────────────────────────
    print(f"\n{_bar()}")
    n_notes = len(distribution)
    print(f"  Analysis complete. {n_notes} distinct note(s) detected across "
          f"{pitched_dur:.1f}s of pitched audio.")
    if raga_matches and raga_matches[0][1] < 0.40:
        print()
        print("  NOTE: Confidence is low. Consider:")
        print("    - Specifying Sa manually:  --sa <note>")
        print("    - Using a cleaner recording (solo instrument/voice)")
        print("    - Trying a longer alaap section")
    print(_bar())
    print()


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def build_parser():
    """Create the command-line argument parser.

    Returns:
        argparse.ArgumentParser

    Example:
        >>> parser = build_parser()
        >>> args = parser.parse_args(['alaap.mp3', '--sa', 'D'])
        >>> args.sa
        'D'
    """
    parser = argparse.ArgumentParser(
        prog='analyze_raga',
        description='Educational Hindustani raga analysis from audio recordings.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python analyze_raga.py yaman_alaap.mp3
              python analyze_raga.py recording.wav --sa D
              python analyze_raga.py concert.mp3 --verbose
        """),
    )
    parser.add_argument(
        'audio_file',
        help='Path to audio file (MP3, WAV, FLAC, OGG, M4A)',
    )
    parser.add_argument(
        '--sa', metavar='NOTE', default=None,
        help='Override auto-detected Sa (tonic), e.g. --sa C  or --sa "D#"',
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show additional technical details in the report',
    )
    return parser


def main():
    """Entry point: parse arguments, run full analysis pipeline, print report.

    Exit codes:
        0 — success
        1 — user error (bad file, missing deps)
        130 — interrupted (Ctrl-C)
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        # 1. Load audio
        print(f"\n  Loading: {args.audio_file} ...")
        y, sr, duration = load_audio(args.audio_file)
        print(f"  Loaded {duration:.1f}s of audio.")

        # 2. Pitch detection
        print("  Detecting pitches (this may take a moment) ...")
        times, freqs, midi_notes, pitch_classes = detect_pitches(y, sr)
        print(f"  Found {len(times)} voiced frames "
              f"({len(times) * FRAME_DURATION:.1f}s of pitched audio).")

        # 3. Detect tonic (Sa)
        sa_pc, sa_note, sa_hz = detect_sa(pitch_classes, sa_override=args.sa)
        tag = "(user-specified)" if args.sa else "(auto-detected)"
        print(f"  Sa = {sa_note} {tag}")

        # 4. Note distribution
        print("  Analyzing note distribution ...")
        distribution = analyze_note_distribution(
            pitch_classes, midi_notes, times, sa_pc
        )

        # 5. Thaat matching
        print("  Matching against thaats ...")
        thaat_matches = identify_thaat(distribution)

        # 6. Raga identification
        print("  Identifying raga ...")
        raga_matches = identify_raga(thaat_matches, distribution)

        # 7. Western mode
        best_thaat = thaat_matches[0][0] if thaat_matches else 'bilaval'
        western_mode = detect_western_mode(best_thaat, sa_note)

        # 8. Print report
        print_report(
            filepath=args.audio_file,
            duration=duration,
            sa_info=(sa_pc, sa_note, sa_hz),
            distribution=distribution,
            thaat_matches=thaat_matches,
            raga_matches=raga_matches,
            western_mode=western_mode,
            verbose=args.verbose,
        )

    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"\n  ERROR: {exc}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(130)


if __name__ == '__main__':
    main()
