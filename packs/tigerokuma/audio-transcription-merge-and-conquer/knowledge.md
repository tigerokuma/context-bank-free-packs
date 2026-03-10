# Merge And Conquer Transcription Notes

## Core Strategy

Transcription speed improves most when the agent reduces end-to-end wall-clock time instead of optimizing one long serial run. The fastest reliable pattern is:

1. inspect the audio
2. normalize it for the chosen ASR backend
3. cut it into overlapping chunks
4. transcribe chunks in parallel
5. merge by timestamp
6. run a narrow repair pass only on uncertain spans

## Chunking Heuristics

- Start with 75 second target chunks for general speech.
- Allow a floor of 45 seconds and a ceiling of 90 seconds.
- Add 2 seconds of overlap so words at chunk boundaries are preserved.
- If voice activity detection is available, move cut points toward silence.
- For dense dialogue with many interruptions, shorten chunks before increasing overlap.

## Merge Rules

- Sort chunk outputs by absolute start time.
- Keep raw text and timestamped text if the backend provides both.
- Resolve overlap in this order:
  1. aligned timestamps
  2. longest common suffix or prefix
  3. lexical similarity on a short token window
- If two candidate lines conflict, keep the higher-confidence line and flag the region.
- Do not collapse repeated words outside the overlap window because they may be intentional speech.

## Repair Pass

Run a second pass only on:

- low-confidence spans
- clipped words at boundaries
- named entities that vary between chunks
- stretches with music, crosstalk, or background noise

This keeps the pipeline fast while still improving quality where it matters.

## Recommended Deliverables

- `transcript.md` with readable paragraphs
- `segments.json` with timestamp ranges and chunk provenance
- `uncertain-spans.md` with exact timecodes
- `summary.md` with a short abstract and action items if relevant
