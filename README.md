# aimidigen

A desktop app that asks an LLM for a note list in strict JSON and writes the result to a `.mid` file.

Chat models are good at describing music and unreliable at emitting well-formed JSON, especially when the response is long enough to hit a token limit and get cut mid-object. This project treats that as the actual engineering problem: the prompt pins the schema down hard, and `parse_json_notes` recovers usable data from truncated replies instead of failing the request. The rest is a PySide6 window with a style prompt, a length selector, a General MIDI instrument picker, and buttons to play or export the file.

## How it works

Everything is in `main.py`, split into a worker thread and a widget.

### `MusicGeneratorThread(QThread)`

1. **Prompt construction.** Builds an instruction that fixes the output schema (`pitch`, `start_time`, `duration`, `velocity`), states the tempo grid as 4/4 with `480 ticks = 1 beat`, gives the requested bar count, constrains velocity to 40 to 100, includes a worked example, and asks for chords by requiring several notes to share a `start_time`. Sent with `temperature: 0.3` and `max_tokens: 2000`.
2. **Request.** A plain `requests.post` to `https://api.groq.com/openai/v1/chat/completions`, the OpenAI-compatible endpoint, with a system message repeating the JSON-only constraint. Non-200 responses emit an empty result and the UI reports failure.
3. **Tolerant parsing.** `parse_json_notes` runs three escalating attempts:
   - `json.loads` on the raw text.
   - Append whichever of `]` and `}` are missing, then retry. This covers the common case where generation stopped one or two characters short.
   - Walk the object list backwards with `re.finditer(r'\{[^}]*\}')`, drop the last complete note, reclose the array, and retry. Repeat until it parses or nothing is left. A reply cut off inside a note object still yields every note before the break.
4. **MIDI writing.** `create_midi_from_notes` sorts notes by `start_time`, groups them with `itertools.groupby`, emits a `program_change` for the selected instrument, and writes `note_on` / `note_off` pairs into a single `mido` track with `ticks_per_beat = 480`. Output goes to `generated_music.mid`, with `get_unique_filename` appending a counter rather than overwriting previous runs.

### `MusicGeneratorApp(QWidget)`

The window holds the style input, a bar-count combo (4, 8, 16, 32), an instrument combo carrying GM program numbers as item data, a progress bar and an animated loading label driven by a `QTimer`. Generation runs on the worker thread and communicates back through two Qt signals, `progress_signal` and `generation_done_signal`, so the UI stays responsive. Playback hands the file to the OS default handler (`os.startfile`, `open` or `xdg-open` by platform); export copies it to a path chosen through `QFileDialog`.

## Tech stack

Python 3, PySide6 for the UI, `mido` for MIDI serialization, `requests` for the HTTP call, Groq's OpenAI-compatible chat completions API as the model backend.

## Getting started

You need a Groq API key.

```bash
pip install PySide6 mido requests
```

Open `main.py` and replace the placeholder on line 11:

```python
API_KEY = "xxx"
```

Then run it:

```bash
python main.py
```

Type a style such as `jazz` or `hip-hop`, pick a length and an instrument, and press the generate button. The raw model output is printed to stdout, which is the fastest way to see what the parser had to work with.

Note that `requirements.txt` is out of date. It pins `pygame`, `python-rtmidi` and `pyfluidsynth`, none of which the current `main.py` imports, and it omits `requests`, which is required. The pip command above reflects the actual imports.

## Status and limitations

A working single-file prototype. Honest about what it is: a tool for generating a starting point to drag into a DAW, not a composition system.

- **Chords are written incorrectly.** `create_midi_from_notes` appends each `note_off` immediately after its `note_on` with `time=duration`. Because `mido` message times are deltas, notes sharing a `start_time` end up sequential rather than simultaneous, so the chords requested in the prompt come out as arpeggios. The source comments flag this as a deliberate simplification, and fixing it means buffering note-off events and scheduling them against absolute time.
- **Timing drifts.** For the same reason, `current_time` is advanced to `start_time` without accounting for the durations already written, so the delta computed for each following group is wrong once any note has been emitted.
- The progress bar is driven by a `msleep(10)` per MIDI message inside the write loop, so it reports an artificial delay rather than real work.
- `API_KEY` is a module-level constant that has to be edited in source. There is no environment variable support and no `.env` handling.
- `MODEL_NAME` is pinned to `llama-3.1-70b-versatile`. Providers retire model identifiers, so this may need updating before the app will run.
- Playback opens the system default `.mid` handler. There is no in-app synthesis, so on a machine with nothing registered for MIDI the play button does nothing useful.
- No tests, no packaging, no retry loop when the model returns unparseable output.

Not implemented, and plausible next steps: correct note-off scheduling, reading the key from the environment, an embedded synth for preview, multi-track output with separate melody and chord tracks, and a seed or history so a good result can be regenerated.

## License

MIT. See [LICENSE](LICENSE).
