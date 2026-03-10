# Transcription Orchestrator Prompt

You are processing one MP3 recording.

Objective:

- finish transcription quickly with a merge-and-conquer workflow
- keep timestamps stable
- avoid hallucinating unheard words

Execution rules:

1. inspect the source file and estimate chunk count
2. normalize audio only if it improves backend reliability
3. split into overlapping chunks with chunk metadata
4. transcribe chunks in parallel
5. merge by absolute time order
6. dedupe overlap conservatively
7. run a repair pass only on low-confidence spans
8. return the final transcript, segment table, uncertainty list, and short summary

When reporting progress, always state:

- total chunk count
- completed chunks
- failed or retried chunks
- whether merge QA found conflicts
