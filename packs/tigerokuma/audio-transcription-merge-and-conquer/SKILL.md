---
name: "Audio Transcription Merge and Conquer"
slug: "audio-transcription-merge-and-conquer"
creatorHandle: "tigerokuma"
category: "automation"
priceType: "free"
tags:
  - "audio-transcription"
  - "speech-to-text"
  - "merge-and-conquer"
  - "parallel-processing"
  - "mp3"
  - "agent"
  - "free-pack"
description: "Context pack for agents that split MP3 audio into parallel transcription jobs, then merge, dedupe, and polish the final transcript quickly."
---

# Audio Transcription Merge and Conquer

Use this pack when an agent receives one MP3 file and must finish transcription with low wall-clock time.

## Goal

- split audio into independent jobs without losing transcript continuity
- run chunk transcription in parallel
- merge overlap cleanly and surface uncertain spans for review

## Recommended Workflow

1. Inspect the source audio.
   - record filename, duration, codec, sample rate, and channels
   - normalize to mono 16 kHz PCM if the transcription backend prefers it
2. Build a chunk plan.
   - target 60 to 90 second chunks
   - keep 2 second overlap on both sides when possible
   - prefer silence-aligned cuts over raw fixed windows
3. Fan out transcription jobs.
   - assign one chunk per worker
   - preserve chunk index, absolute start time, absolute end time, and overlap metadata
   - retry only failed or low-confidence chunks instead of rerunning everything
4. Merge and conquer.
   - sort chunks by absolute start time
   - remove duplicate overlap text using timestamps first and lexical similarity second
   - prefer the higher-confidence wording when two chunks disagree in the overlap region
5. Polish the final result.
   - restore punctuation and paragraph breaks
   - keep timestamps or segment markers
   - emit a short uncertainty report instead of guessing unheard words

## Output Contract

- a full transcript in reading order
- a time-indexed segment table
- an uncertainty list for low-confidence regions
- a short summary of the recording

## Quality Rules

- never invent words that were not heard
- mark unintelligible audio explicitly
- keep the merge deterministic so reruns stay comparable
- save intermediate chunk outputs until final QA passes

## Safe Usage Notes

- use public-safe prompts and metadata only
- do not include API keys, private recordings, or download-and-execute shell snippets
- prefer bounded concurrency so the system stays stable under long recordings
