# Audio Plugins

Alcove wraps existing audio analysis libraries. It does not reimplement signal processing. Each plugin registers an extractor for one or more file extensions and returns structured metadata that lands in the index alongside the source file.

## Speech Transcription

**Library:** [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)

Transcribes any spoken audio to time-coded text. Use it for oral histories, interviews, lectures, field notes, voice memos. Each chunk carries a start and end timestamp so queries can return a playback position, not just a filename.

Faster-Whisper runs locally. Audio never leaves the machine.

## Speaker Diarization

**Library:** [`pyannote.audio`](https://github.com/pyannote/pyannote-audio)

Segments audio by speaker identity. Each segment gets a label (SPEAKER_00, SPEAKER_01, etc.). Combine with the transcription plugin: every text chunk carries both a timestamp and a speaker tag. Useful for multi-participant interviews, council recordings, panel discussions.

Note: pyannote models require accepting a license on Hugging Face before download.

## Semantic Audio Search

**Library:** [`laion-clap`](https://github.com/LAION-AI/CLAP)

CLAP (Contrastive Language-Audio Pretraining) embeds audio clips and text queries in a shared vector space. You can query with a text description: "rain on a metal roof," "crowd applause," "someone laughing." No transcription required. Works on any audio, not just speech.

## Sound Classification

**Library:** [YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet) via [`tensorflow`](https://www.tensorflow.org)

Classifies audio against 521 sound event categories from Google's AudioSet taxonomy. Outputs confidence scores per category. Use it to tag mixed archives automatically, or to filter a large collection down to a specific sound type before deeper analysis.

## Music Fingerprinting

**Libraries:** [`pyacoustid`](https://github.com/beetbox/pyacoustid), [`chromaprint`](https://acoustid.org/chromaprint)

Identifies recordings by acoustic fingerprint against the [AcoustID](https://acoustid.org) database. Returns [MusicBrainz](https://musicbrainz.org) identifiers when a match is found. Useful for personal music libraries, digitized tape collections, or copyright scanning workflows.

## Bioacoustics

**Libraries:** [`birdnetlib`](https://github.com/joeweiss/birdnetlib), [`opensoundscape`](https://github.com/kitzeslab/opensoundscape)

Detects species from field recordings: birds, bats, frogs, marine mammals. Returns species name, timestamp, and confidence score per detection. See the [Birding detail file](birding.md) for how this connects to eBird and other ornithology data sources.

## Ocean Hydrophone Archives

**Libraries:** [`soundfile`](https://github.com/bastibe/python-soundfile), [`scipy`](https://scipy.org)

Indexes passive acoustic monitoring archives: whale calls, shipping vessel noise, seismic events. Institutions running long-term hydrophone arrays accumulate recordings that are impractical to review manually. This plugin extracts metadata and enables time-range queries over large archives. Data stays at the institution.
