# whisper-subtitle

Convert OpenAI Whisper JSON transcription output to SRT or WebVTT subtitle files.

## Usage

```bash
# Convert to SRT (default)
python tools/whisper-subtitle/subtitle.py transcript.json -o subtitles.srt

# Convert to WebVTT
python tools/whisper-subtitle/subtitle.py transcript.json --format vtt -o subtitles.vtt

# Split long segments into short captions (max 8 words per cue)
python tools/whisper-subtitle/subtitle.py transcript.json --max-words 8

# Remove filler words (uh, um, hmm)
python tools/whisper-subtitle/subtitle.py transcript.json --strip-filler

# Write to stdout
python tools/whisper-subtitle/subtitle.py transcript.json
```

## Input format

Accepts any Whisper JSON output. Both formats are supported:

**Dict format** (standard `whisper` CLI output):

```json
{
  "text": "...",
  "segments": [
    {"start": 0.0, "end": 3.2, "text": "Hello world."},
    {"start": 3.2, "end": 6.8, "text": "This is a subtitle."}
  ]
}
```

**List format** (some Whisper variants):

```json
[
  {"start": 0.0, "end": 3.2, "text": "Hello world."},
  ...
]
```

## Output formats

### SRT

```text
1
00:00:00,000 --> 00:00:03,200
Hello world.

2
00:00:03,200 --> 00:00:06,800
This is a subtitle.
```

### WebVTT

```text
WEBVTT

00:00:00.000 --> 00:00:03.200
Hello world.
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--format` | `srt` | Output format: `srt` or `vtt` |
| `--max-words N` | — | Split segments longer than N words into equal-duration cues |
| `--strip-filler` | off | Remove filler words: `uh`, `um`, `hmm` |
| `-o FILE` | stdout | Output file path |

## Dependencies

No external dependencies — stdlib only.
