# Project bundles

When the script and scene-drawing code are already written, produce the video
from a small **project bundle**: script data, scene and art code, optional
assets, and a manifest. Media never travels with the bundle — the machine that
renders runs TTS, draws frames, mixes audio and writes the MP4 locally.

Incoming bundles can land in `~/explainer-bundles/<slug>/` (override with
`EXPLAINER_BUNDLES_DIR`). Pack with `explainer pack <dir>`, copy the tarball or
directory with whatever file-copy tool you use, then `explainer build <slug>`.

The main `explainer run "topic"` flow (Claude or Grok writer + Cairo plan
renderer) is unchanged. Use a bundle when you already have the scene code.

## Directory layout

```
<slug>/
  manifest.yaml     # required; schema below
  script.py         # required; SCENES
  scenes.py         # required; SCENE_FUNCS and optional sfx_events
  art_gas.py        # optional project-specific art (list in manifest.modules)
  assets/           # optional extra files
  script.md         # optional, human-readable; ignored by the builder
```

Shared helpers are **not** copied into the bundle. Scene code may still write:

```python
from lib import *
from art import label, card
from art_pro import *
```

The loader injects `explainer.draw.lib`, `explainer.draw.art` and
`explainer.draw.art_pro` as those names.

## `manifest.yaml`

| Field | Required | Default | Notes |
|---|---|---|---|
| `schema` | yes | — | Must be `explainer-bundle/v1` |
| `title` | yes | — | Shown in metadata and QA |
| `slug` | yes | — | kebab-case; build and output folders |
| `voice` | no | `kokoro:af_heart` | `kokoro:af_heart`, `elevenlabs:max`, `elevenlabs:todd`, or any `engine:name` the pipeline already knows. `--voice` overrides. |
| `output` | no | `<slug>.mp4` | Filename of the finished video |
| `aspect` | no | `16:9` | `16:9` or `9:16` |
| `fps` | no | `30` | |
| `width`, `height` | no | 1920×1080 (or 1080×1920) | Design resolution. Scenes draw in 1920×1080 space; the renderer may scale the output. |
| `script` | no | `script.py` | |
| `scenes` | no | `scenes.py` | |
| `modules` | no | `[]` | Extra `.py` files to import (project art) |
| `assets` | no | `[]` | Extra files that must be present |
| `timing.lead` | no | `0.7` | Silence before the first sentence of a scene (s) |
| `timing.tail` | no | `1.0` | Hold after the last sentence (s) |
| `timing.gap` | no | `0.55` | Pause between sentences (s) |
| `timing.comma_gap` | no | `0.22` | Pause after a caption that ends with a comma |
| `timing.tails` | no | `{}` | Per-scene tail override, e.g. `{close: 4.5}` |
| `timing.speed` | no | voice preset | TTS speed override for this bundle |

## `script.py`

```python
SCENES = [
    ("hook", "Behind the flame", [
        ("Caption text shown on screen.", None),
        ("Caption.", "Optional spoken form if it differs."),
    ]),
]
```

Each scene is `(id, title, sentences)`. Each sentence is
`(caption, tts_or_None)`.

## `scenes.py`

```python
from lib import *

def hook(c, t, T):
    # c = skia canvas, t = seconds from scene start
    # T.s / T.e = sentence start/end lists; T.w('word', default) = word time
    text(c, "Hello", 960, 400, 64, WHITE, 1, "bold")

SCENE_FUNCS = {"hook": hook}

def sfx_events(TM, words=None):
    # optional: [(scene_id, local_time, kind), ...]
    # kinds: blip, tick, whoosh, whoosh_soft, hiss, drip, chime, rumble, crack, click, ...
    return []
```

Draw in the 1920×1080 design space. Captions and the scene-title chip are burned
in by the renderer (dark rounded pill, Poppins).

## Commands

```bash
explainer pack examples/how-natural-gas-gets-to-your-home
# -> how-natural-gas-gets-to-your-home.tgz  (code only)

explainer build examples/how-natural-gas-gets-to-your-home
explainer build ~/explainer-bundles/how-natural-gas-gets-to-your-home
explainer build how-natural-gas-gets-to-your-home          # searches landing + examples/

explainer build <bundle> --voice elevenlabs:max
explainer build <bundle> --scene hook                      # one scene
explainer build <bundle> --still hook:2.5                  # PNG at t=2.5s
explainer build <bundle> --detached                        # log + JSON pid, returns
explainer status <bundle> --json                           # poll progress / outputs
```

Stages (cached and resumable): `voice` → `render` → `music` → `assemble` →
`share` → `qa` → `deliver`.

Outputs land in `out/<slug>/16x9/`:

- `<output>.mp4` — 1080p H.264 + AAC
- `<output>-share.mp4` — under 25 MB
- `qa.json`, `qa.md`, `contact_sheet.jpg`, `poster.png`
- a copy of the MP4 in `EXPLAINER_DELIVER_DIR` when that is set

## Setup (bundle extras)

```bash
brew install python@3.12 ffmpeg
make setup PYTHON=python3.12
make setup-bundle            # skia-python, scipy, soundfile, pyloudnorm
# optional: whisper-cli + a ggml model for word-timed SFX and the ASR check
#   EXPLAINER_WHISPER_MODEL=~/.cache/whisper/ggml-base.en.bin
```

`~/.config/explainer/config`:

```bash
EXPLAINER_DELIVER_DIR=~/Movies/explainers
EXPLAINER_BUNDLES_DIR=~/explainer-bundles
# EXPLAINER_VOICE=kokoro:af_heart     # optional default for the writer path
```

ElevenLabs keys stay in `ELEVENLABS_API_KEY` or `~/.config/explainer/elevenlabs.env`.
Poppins is vendored under `explainer/fonts/Poppins/` (OFL). Override with
`EXPLAINER_FONT_DIR` if you install the family yourself.
