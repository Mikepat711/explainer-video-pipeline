# Explainer Video Pipeline

Turn a technical topic into a polished theory explainer video: clean modern motion graphics, a
natural-sounding narrator, a procedural music bed with ducking and sound design, burned-in captions
plus an SRT, and a 1080p H.264/AAC MP4 with a poster frame.

```bash
make video TOPIC="how GPS works"
# -> out/how-gps-works/16x9/how-gps-works.mp4 (+ .srt, poster.png/jpg, qa.md, frames/)
```

Research, the script and a lesson-specific visual plan are written by Claude (Opus by default) through
the [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI you are already signed in to; the
repo holds no API keys (see [Script writer](#script-writer-claude-code)). The renderer then draws that
plan with purpose-built mechanism animations (spinning rotors, power flows, gauges, relays, transformers)
timed to the narration, rather than filling in slide templates (see [Visual plan renderer](#visual-plan-renderer)).
Everything else runs locally.
Narration uses [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), an 82M-parameter open-weight neural
voice run through ONNX Runtime, with Chatterbox, Parler, Piper and espeak-ng as alternatives.

A lesson covers about 350 words of narration, read at a conversational ~160 words per minute with
breathing pauses between sentences, so finished videos run about 2.5 to 3 minutes.

## Quick start on a Mac (Apple Silicon)

1. Install the command-line tools and [Homebrew](https://brew.sh) if you don't have them yet:

   ```bash
   xcode-select --install
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. Install Python, ffmpeg and the cairo graphics library:

   ```bash
   brew install python@3.12 ffmpeg cairo pkg-config
   brew install --cask font-inter      # optional: the design font (falls back to DejaVu Sans)
   ```

   Burned-in captions need an ffmpeg build with libass, which Homebrew's plain `ffmpeg` lacks. Install
   `brew install ffmpeg-full` as well: the pipeline finds it on its own (or set `EXPLAINER_FFMPEG`, see
   [Machine-local settings](#machine-local-settings)) and checks before a run starts.

3. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and sign in once
   (`claude` in a terminal). The pipeline runs it headlessly; check with
   `claude -p "say ok" --model opus --output-format json < /dev/null`.

4. Get the code and install the Python dependencies into `.venv`:

   ```bash
   git clone https://github.com/Mikepat711/explainer-video-pipeline.git
   cd explainer-video-pipeline
   make setup PYTHON=python3.12
   ```

5. Make a video (the first run downloads the Kokoro voice model, about 350 MB, into `.cache/voices/`):

   ```bash
   make plan TOPIC="how the electrical grid works"    # optional: research, script and visual plan only
   make video TOPIC="how the electrical grid works"
   open out/how-the-electrical-grid-works/16x9/how-the-electrical-grid-works.mp4
   ```

### Picking a voice

The narrator is one line in `config.yaml`:

```yaml
voice:
  use: kokoro:af_heart    # <- THE NARRATOR VOICE
```

To use a different voice on one machine without touching the repo, add one line to
`~/.config/explainer/config`:

```bash
EXPLAINER_VOICE=kokoro:bm_george
```

For a single run: `ARGS="--set voice.use=kokoro:bm_fable"`. The default narrator, af_heart, speaks at
its natural pace: preset speed 0.85 (about 155 words per minute while talking) with `target_wpm: 0`, so it
is never re-synthesized faster or time-stretched to hit a length. Squeezing speech to a words-per-minute
target that counts the pauses made narration sound rushed: the more pauses a script had, the faster the
words were pushed. Scripts are written in short sentences instead, and each sentence break is a pause.
The other presets still use `voice.target_wpm`, 165 ± 4%: the preset's own speed is kept when the result is
inside that window; otherwise the narration is re-synthesized once at a corrected speed, and a gentle
time-stretch closes any gap that remains. Set a preset's `target_wpm: 0` to keep its natural speed.
`timing.json` and `qa.md` record the pace, speed and stretch that were used.

| `voice.use` | Voice | Notes |
|---|---|---|
| `kokoro:af_heart` | American female, warm and soft | Default; speed 0.85, natural pace (~155 wpm while talking) |
| `kokoro:af_bella` | American female, bright and clear | Speed 0.88 |
| `kokoro:am_michael` | American male, steady and neutral | Speed 0.96 |
| `kokoro:bm_george` | British male, mature documentary narrator | Speed 0.96 |
| `kokoro:bm_fable` | British male, younger and lively | Speed 0.85 |
| `chatterbox` | Expressive male (Resemble AI, MIT; output is watermarked) | `make setup-chatterbox`; time-stretched to pace |
| `parler:Jon` | Parler-TTS mini, male (Apache-2.0) | `make setup-parler`; time-stretched to pace |

Any other Kokoro id works too (`kokoro:<id>`; `af_`/`am_` are American female/male, `bf_`/`bm_`
British). Piper (`piper:en_US-ryan-high`), espeak (`espeak:en-us`), an OpenAI-compatible endpoint
(`openai`) and any CLI (`command` with `voice.command`, e.g. macOS `say -o {out} {text}`) are also
available. Chatterbox and Parler run PyTorch in their own virtualenvs (`.venv-chatterbox`,
`.venv-parler`) so their pinned versions never clash with the main one. On Apple Silicon they use the
GPU (MPS) when it works and fall back to the CPU.

```bash
make voices                      # every preset reads the same paragraph -> out/voices/voice-*.mp3
make voices ARGS=--list          # presets, what is installed, and every Kokoro voice id
make voices VOICES=kokoro:af_heart,kokoro:bm_george,chatterbox
```

Numbers, units, years and common acronyms are spelled out before synthesis ("400,000 V" becomes "four
hundred thousand volts"). Add your own spoken forms under `voice.pronounce`. Each sentence is cached per
voice, so switching voices only re-synthesizes the narration.

## Script writer (Claude Code)

Three stages write the lesson, each a headless call to the Claude Code CLI:

| Stage | Output (`build/<slug>/common/`) | What Claude writes |
|---|---|---|
| `research` | `research.json`, `research.md` | Key concepts with the mechanism behind each, the process in order, numbers with sources, misconceptions. Web search and fetch are allowed. |
| `script` | `script.json`, `script.md` | Title and scenes (as many as the topic needs); per scene the concept, the narration as numbered sentences, and the idea for the teaching animation. |
| `plan` | `plan.json`, `plan.md` | The visual/animation plan in the engine's own vocabulary: style, actors (generators, transformers, power lines, gauges, flows, charts…), beats synced to sentences (`s2+0.5`), camera moves and continuous shots. |

Each call is `claude -p <prompt> --model <model> --output-format json`, with stdin closed, an empty working
directory, and file and shell tools disabled. The reply must be one JSON document that passes the stage's
JSON schema and semantic checks: one sentence per sync point, every reference resolves, each scene has
a mechanism animation, on-screen text stays short. Otherwise the call is retried with the errors fed
back (`llm.retries`), and a call that overruns `llm.timeout` is killed. Every stage is cached, so
re-running costs nothing unless the topic, settings or code changed. `*.meta.json` records the model,
attempts and duration.

The plan prompt lists every hard limit up front: the exhaustive enum values (for example, the network
node kinds), character and word caps, numeric ranges, the id pattern and per-scene actor/beat caps.
Cosmetic slips are repaired before validation instead of costing a retry: an unknown network node
kind such as `consumer` becomes its nearest allowed kind (`load`). The prompt also has an honest-scale
rule. Whenever a visual magnifies an effect so it can be seen (one kettle visibly moving the grid's
frequency, an atom drawn huge), the plan must label it on screen ("exaggerated for illustration", "not
to scale") or show a cause big enough to produce it. Such notes must be as legible as other labels, and
one set in the smallest type size is raised to the size other notes use.

Run only these stages with `make plan TOPIC="..."` (or `python -m explainer run "..." --until plan`).

- **Model**: `llm.model` in `config.yaml` (default `opus`), or `EXPLAINER_LLM_MODEL=opus` in
  `~/.config/explainer/config`.
- **Binary**: `claude` on PATH or the standard `~/.local/bin/claude` install; otherwise set
  `EXPLAINER_CLAUDE_BIN`.
- **Fallback**: if the CLI is missing, signed out or keeps failing, the stages fall back to an
  extractive writer (topic-pack sources, `--source` URLs, or Wikipedia as a last resort). That is only a
  placeholder: a banner is printed on stderr, `qa.md` opens with a warning, and the
  `no_fallback_writer` QA check fails. The next run retries Claude automatically. Runs with `--fresh` or
  with required topics never fall back: they stop with the reason instead.
- A topic pack's hand-authored `research.md`, `script.md` or `plan.json` wins over Claude unless you pass
  `--fresh`, which sets those files aside so Claude writes new ones. A topic without pinned files is
  unaffected by `--fresh`, so nothing re-runs.

### Briefs: required topics and notes

A brief tells the writer what the lesson must cover. It comes from `topics/<slug>/brief.md` (read
automatically), any `--brief FILE`, and `--require "id: what to cover"` (repeatable). A later source
replaces a required topic with the same id.

```markdown
---
config:                      # optional config overrides for this topic
  length: {target_seconds: 240, max_seconds: 300}
---
# Brief: how the electrical grid works
## Required topics
- wind: moving air turns the blades and the rotor drives a generator in the nacelle
- line-faults: relays detect a fault and breakers isolate only the faulted section
## Notes
Everything outside "Required topics" (except the title and HTML comments) goes to the writer as notes.
```

Every writer prompt lists the required topics and notes, and the validators enforce them, so a reply
that misses one is retried with the errors fed back:

- **research** must report each id under `required_topics`.
- **script** must list each id in the `covers` of the scene that teaches it.
- **plan** must give each id its own visual: a non-text actor with `"covers": "<id>"` that a `set`,
  `move` or `trace` beat animates. An actor covers one id, so two topics never share a visual.
  `plan.md` lists which actor shows which topic.

A pinned plan that misses required topics only logs warnings; `--fresh` asks Claude for one that covers
them. The topic brief's `config:` sits between `config.yaml` and `--config`/`--set`. The grid brief uses
it to raise the word budget for its six extra topics.

## Visual plan renderer

`render` draws `plan.json` directly. Each scene is a set of actors placed on a 1600×900 design canvas
and a list of beats tied to the narration (`s3+0.4` means 0.4 s after sentence 3 starts, `e3` when it
ends). The beat actions are `enter`, `exit`, `set`, `move`, `pulse`, `trace` and `camera`. Every actor
kind has its own drawer that shows the mechanism rather than a picture of it:

- **Rotating machines** (`generator`, `rotor`, `gear`, `chain`) integrate their speed over time, so a
  generator that slows down really falls behind in phase. A shared spin budget keeps rotors under about
  75 visual rpm so they never strobe or appear to run backwards at 30 fps.
- **Flows and lines** (`powerline`, `cable`, `flow`, `network` edges) move particles along their path at
  a speed and density that follow the animated power. A `breaker` snaps its contact open with a spark.
- **Readouts** (`gauge`, `meter`, `badge`, `text`) tween their values with the narration and change
  zone colour as they cross thresholds such as a 59.3 Hz load-shed line.
- **Physical pieces** (`transformer`, `coil`, `field`, `wave`, `balance`, `spring`, `lever`, …) animate
  the quantity they illustrate: turns ratio, field lines, phase, the tilt of supply against demand.
- **Camera** moves pan and zoom between regions. Readouts and labels stay readable while zoomed:
  they are counter-scaled, kept inside the visible area above the captions, and fade out instead of
  showing a clipped sliver at the frame edge. A scene can `inherit` the previous scene's final state for
  continuous shots.

`render` also runs a layout check. It probes each scene at mid-scene, just before the cut and after
every reveal or camera move, and reports text that overlaps other text, leaves the frame, enters the
caption band, or is set visible but never appears on screen. The results go to `layout_report.json` and
`qa.md`.

To iterate on a plan without waiting for a render, use `make frames TOPIC="..."`. It writes still frames
plus a contact sheet from `plan.json` in a few seconds, using the narration timing when the voice stage
has run and estimating from word counts otherwise.

Topic packs with a legacy `shots.yaml`, and plans from the offline fallback writer, still use the
template renderer. `render.engine` forces one or the other.

[`examples/how-a-bike-derailleur-works/`](examples/how-a-bike-derailleur-works/) is a contrast example:
a hand-sized mechanism (gears, chain, a parallelogram linkage, a sprung cage) drawn from the same
vocabulary as the grid lesson but with no actors, style or staging in common with it.

## Machine-local settings

`~/.config/explainer/config` (or the file named by `EXPLAINER_CONFIG`) holds per-machine settings as
shell-style `KEY=VALUE` lines. Environment variables with the same names override the file, the file
overrides `config.yaml` and `--config`, and `--set` overrides everything. Nothing secret goes here;
Claude Code keeps its own sign-in.

```bash
# ~/.config/explainer/config
EXPLAINER_VOICE=kokoro:af_heart        # narrator (voice.use)
EXPLAINER_LLM_MODEL=opus               # Claude model alias (llm.model)
# EXPLAINER_CLAUDE_BIN=/path/to/claude # only if `claude` is not on PATH (llm.claude_bin)
# EXPLAINER_LLM_TIMEOUT=900            # seconds per Claude call (llm.timeout)
# EXPLAINER_LLM_RETRIES=2              # extra attempts after a bad reply (llm.retries)
# EXPLAINER_LLM=off                    # force the offline fallback writer (llm.writer)
# EXPLAINER_FFMPEG=/path/to/ffmpeg     # an ffmpeg with libass for burned-in captions
```

## Setup on Linux

Requirements: Python 3.10+, `ffmpeg` built with libass (standard distro builds are), and the cairo
headers for `pycairo`.

```bash
sudo apt install ffmpeg libcairo2-dev pkg-config python3-venv espeak-ng   # espeak-ng is optional
make setup
```

Voice models download automatically on first use into `.cache/voices/`. Set `EXPLAINER_VOICE_DIR` to
put them somewhere else.

## Usage

| Command | What it does |
|---|---|
| `make video TOPIC="how GPS works"` | Full pipeline, 16:9. Cached stages are skipped. |
| `make plan TOPIC="..."` | Only research, script and visual plan (Claude), into `build/<slug>/common/`. |
| `make plan TOPIC="..." ARGS="--fresh"` | The same, ignoring the topic pack's pinned research/script/plan (Claude writes new ones that cover the topic's brief). |
| `make vertical TOPIC="..."` | Full pipeline in 9:16 (`configs/vertical.yaml`). |
| `make short TOPIC="..." SCENES=hook,signal` | 9:16 render of selected scenes only (output tag `short`). |
| `make voices [VOICES=engine:voice,...]` | Voice comparison clips of the same paragraph, loudness-matched. |
| `make share VIDEO=out/.../x.mp4 [MAX_MB=15]` | Size-capped copy for chat or email (2-pass H.264, AAC 128k, faststart). |
| `make stage STAGE=music TOPIC="..."` | Force re-run of a single stage using cached upstream outputs. |
| `make status TOPIC="..."` | Show which stages are cached or stale. |
| `make frames TOPIC="..." [PER_SCENE=4]` | Still frames plus a contact sheet drawn from the visual plan (no render needed). |
| `make preview TOPIC="..."` | Render still frames of each scene from the timeline (fast layout iteration, no encoding). |
| `make samples` | Build the two bundled samples plus a short 9:16 proof. |
| `make test` | Unit tests (the Claude CLI is mocked; nothing is sent anywhere). |
| `make setup-chatterbox`, `make setup-parler` | Optional PyTorch voices, each in its own virtualenv. |

The CLI can also be called directly:

```bash
.venv/bin/python -m explainer run "how a heat pump works" --aspect 9:16 --set voice.use=kokoro:bm_george
.venv/bin/python -m explainer run "how the electrical grid works" --until plan   # writer stages only
.venv/bin/python -m explainer run "how lidar works" --source https://en.wikipedia.org/wiki/Lidar
.venv/bin/python -m explainer run "how lidar works" --until plan --require "tof: timing a laser pulse's round trip"
.venv/bin/python -m explainer run "how GPS works" --from render      # force re-run from a stage on
.venv/bin/python -m explainer stage captions "how GPS works" --force
.venv/bin/python -m explainer share out/how-gps-works/16x9/how-gps-works.mp4 --max-mb 15
.venv/bin/python -m explainer frames "how the electrical grid works" --per-scene 4 --out previews/grid
.venv/bin/python -m explainer stages                                 # list stages
```

## Pipeline stages

Each stage writes to `build/<topic-slug>/…` and records a stamp. The stamp's fingerprint covers the
stage's own source code, its declared config sections and inputs, and the result hashes of upstream
stages. A stage re-runs only when something it depends on changed. Stages marked *common* are
aspect-independent and shared between 16:9 and 9:16 variants.

When a common stage produces a different result, the outputs of every common stage downstream of it
are deleted before anything else runs. A file left by an older build (an old shot list, voice tracks
for scenes that no longer exist) can therefore never reach a render.

| # | Stage | Scope | Output | Notes |
|---|---|---|---|---|
| a | `research` | common | `research.json`, `research.md`, `sources.json` | Claude researches the mechanism (web search allowed), using any topic-pack sources and `--source` URLs. Fallback: extractive, from those sources or Wikipedia. |
| b | `script` | common | `script.json`, `script.md` | Claude writes the narration as numbered sentences plus a teaching idea per scene. A topic-pack `script.md` wins. |
| c | `plan` | common | `plan.json`, `plan.md` | Claude designs the lesson's visual/animation plan (actors, sentence-synced beats, camera). A topic-pack `plan.json` wins. |
| – | `shots` | common | `shots.json`, `shots.md` | Template shot list, only for legacy `shots.yaml` packs and the fallback path. When the plan renders the topic it writes an explicit "unused" stub, which the timeline refuses to render. |
| e | `voice` | common | `voice/<scene>.wav`, `timing.json` | Pluggable TTS, synthesized and cached per sentence for exact caption and animation timing, paced to `voice.target_wpm`. Pauses grow slightly after long sentences. Tracks for scenes no longer in the script are removed. |
| – | `timeline` | variant | `timeline.json` | Resolves the plan's beat times (`s2+0.5`, `e2`) against the narration and sets scene durations: the narration, stretched if needed so every reveal stays up for `reveal_hold` seconds and the on-screen text can be read at `reading_wpm`. Emits sound-design cues and scene transitions. |
| d | `render` | variant | `scenes/*.mp4`, `poster.png`, `layout_report.json` | Draws the visual plan with Cairo, piped into ffmpeg, rendered in parallel and cached per scene. Includes the layout check (see [Visual plan renderer](#visual-plan-renderer)). |
| f | `music` | variant | `audio/music.wav`, `audio/sfx.wav` | Procedural score (pads, arpeggio, bass, soft drums, synthetic reverb) plus whooshes, pops and impacts. Pure numpy, so there are no licensing issues. |
| – | `mix` | variant | `audio/mix.wav`, `mix_report.json` | Voice-driven ducking (lookahead, attack/release), a true-peak limiter, and two-pass linear EBU R128 loudnorm (default -16 LUFS / -1.5 dBTP). |
| g | `captions` | variant | `captions.srt`, `captions.ass` | Balanced 2-line cues with no orphan words; the ASS file is styled and burned in. |
| h | `assemble` | variant | `out/<slug>/<variant>/<slug>.mp4`, `.srt`, `poster.png/jpg` | Scenes joined with crossfades; H.264 High, yuv420p, AAC 48 kHz stereo, faststart. All input metadata is stripped; only a title tag is added. |
| – | `qa` | variant | `qa.json`, `qa.md`, `frames/`, `contact_sheet.jpg` | ffprobe checks, ebur128 loudness and true peak, blackdetect, sampled-frame blank detection (including both sides of every cut), the layout report, the narration pace, and who wrote research/script/plan (a fallback writer fails the `no_fallback_writer` check). |

## Configuration

`config.yaml` holds the defaults. You can layer extra files on top with `--config file.yaml`, which is
repeatable and deep-merged, then [machine-local settings](#machine-local-settings) apply, and
`--set key=value` overrides single values last.

- **Voice** (`voice.*`): `use` (the narrator, see [Picking a voice](#picking-a-voice)), `presets` (per-voice
  settings such as Kokoro `speed` or Chatterbox `exaggeration`), `target_wpm` and `pace_tolerance`,
  `pronounce`, and engine options (Piper and espeak voices, the Chatterbox/Parler virtualenv paths,
  `torch_device`).
- **Writer** (`llm.*`): `writer` (`claude` or `off`), `model`, `claude_bin`, `timeout`, `retries`,
  `web_research`, `extra_args` (appended to every `claude` call). See [Script writer](#script-writer-claude-code).
- **Length and pacing** (`length.*`): `target_seconds` and `words_per_minute` set how much content a
  generated script covers. `max_seconds` is how far the finished video may flex. `scene_lead_in`,
  `sentence_gap`, `sentence_gap_extra` and `scene_tail` control the pauses. `min_scene`, `reveal_hold`
  and `reading_wpm` make sure every scene stays up long enough to read.
- **Style** (`style.*`): `theme` (`midnight` dark or `paper` light), `accent` colour, `font`, background
  grid, progress bar. `motion` stretches every animation (1.0 is snappy, 1.6 is the calm default),
  `overshoot` sets how much pop-in elements bounce, and `crossfade` sets the dissolve between scenes.
- **Aspect** (`video.aspect`): `"16:9"` (1920×1080) or `"9:16"` (1080×1920). Every template has a
  portrait layout, and captions sit above the platform-UI zone in 9:16.
- **Audio** (`audio.*`): loudness target, true peak, music on/off, BPM, key, bed level, ducking depth, SFX
  level.
- **Captions** (`captions.*`): burn-in on/off, max characters per line for each aspect.
- **Render** (`render.*`): `engine` (`auto` draws the visual plan and uses templates only for legacy
  `shots.yaml` packs and fallback plans; `plan` or `templates` forces one), parallel `workers`, and
  `scene_timeout`, after which a hung scene render fails the stage instead of stalling it.

## Topic packs and the shot-list format

A topic pack lives in `topics/<topic-slug>/`. The slug is the lower-case, hyphenated topic, e.g.
`how-gps-works`. It can contain:

- `sources/*.md|txt`: source documents for research.
- `sources.txt`: URLs to fetch, one per line.
- `research.md`, `script.md`, `plan.json`, `shots.yaml`: hand-authored overrides for those stages
  (`--fresh` sets the writer outputs aside).
- `brief.md`: required topics, notes and config for the writer (see Briefs above).

`topics/how-the-electrical-grid-works/` pins the research, script and plan that Claude Opus wrote for the
grid lesson, so the final render uses exactly the reviewed version. Its `brief.md` asks the next rewrite
to cover the plant types (thermal, hydro, wind, solar), line faults and protection, and black start;
`make plan TOPIC="how the electrical grid works" ARGS="--fresh"` produces it. The plan's `provenance` block
records the writer and every hand edit made in review: on-screen "exaggerated for illustration" labels
where one kettle visibly moves the grid, a kettle icon, and two labels moved into view.

Available scene templates: `title`, `bullets`, `diagram` (nodes and animated flow edges), `cycle` (closed
loop with coloured segments, zones and heat arrows), `cutaway` (layered cross-section with callouts and
a signal ray), `stat` (count-up number with bars), `compare`, `steps`, `orbit`, `signal` (time of
flight), `trilateration` (auto-fitted circles, optional uncertainty bands), and `recap`. Any template
can also take `notes` callouts. The field reference is `TEMPLATE_DOC` in `explainer/gfx/scenes.py`; the
two bundled packs are complete examples.

Timing values accept seconds, `sN` / `eN` (start or end of narration sentence *N*, optionally `+0.5`),
or `end-1.5`.

## Plugging in providers

- **Writer**: the Claude Code CLI (see [Script writer](#script-writer-claude-code)). Extra CLI flags can
  go in `llm.extra_args`.
- **TTS**: `voice.use: openai` uses an OpenAI-compatible `/audio/speech` endpoint with `OPENAI_API_KEY`
  from your environment. `voice.use: command` runs any CLI, e.g. macOS `say`. To add an engine, subclass
  `TTSEngine` in `explainer/tts/__init__.py` and register it in `ENGINES`.

## Samples

`make samples` builds:

- `out/how-gps-works/16x9/how-gps-works.mp4`: 8 scenes, orbit / time-of-flight / trilateration /
  relativity / cutaway.
- `out/how-a-heat-pump-works/16x9/how-a-heat-pump-works.mp4`: 8 scenes, compare / diagram / refrigerant
  cycle / COP.
- `out/how-gps-works/9x16-short/how-gps-works.mp4`: a 3-scene vertical proof.

Each output folder also contains `qa.md` with integrated LUFS, true peak, codec checks and frame-check
results. On a 4-core Linux VM a 2.5-minute video renders in about 3 to 4 minutes. Rendered media is not
committed to git.

## Known limitations

- The fallback writer (used only when Claude is unavailable) is extractive. Its output is a placeholder,
  and QA flags it.
- Visuals are procedural 2D vector graphics from a fixed vocabulary of actor kinds and icons; there is
  no stock footage or 3D. A topic that needs a mechanism the vocabulary lacks gets a simpler stand-in.
- Plans are designed for 16:9. In 9:16 the frame crops to each scene's `portrait_focus`, so side labels
  or readouts outside that area can be cut off. Check vertical renders with `make frames` before
  publishing.
- The layout checker verifies text-to-text overlaps, frame bounds, the caption band and text that never
  appears on screen. Text crossing a graphic is left to the contact sheet (`make frames`) and QA frames.
- Kokoro reads each sentence on its own, so intonation doesn't carry across sentences the way a human
  reading a whole paragraph would. Unusual acronyms may need a spelled-out form (`voice.pronounce`).
- The bundled voices are English-first. Other languages need a matching Kokoro or Piper voice and
  topic-pack content.

## License

MIT. See [LICENSE](LICENSE).
