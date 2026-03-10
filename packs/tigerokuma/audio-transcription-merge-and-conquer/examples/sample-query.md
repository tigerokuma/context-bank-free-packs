# Sample Query

Transcribe `audio-data.mp3` as fast as possible.

Use a merge-and-conquer workflow:

- split the audio into overlap-aware chunks
- run chunk transcription in parallel
- merge the result into one transcript with timestamps
- list any uncertain spans separately instead of guessing
