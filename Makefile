PYTHON  ?= python3
PY      ?= .venv/bin/python
TOPIC   ?= how GPS works
CONFIG  ?=
STAGE   ?= render
ARGS    ?=
CFGARG  := $(if $(CONFIG),--config $(CONFIG),)

VOICES  ?=
VIDEO   ?=
MAX_MB  ?= 15
PER_SCENE ?= 4

.PHONY: setup setup-chatterbox setup-parler plan video vertical short stage status preview frames clean samples test voices share

setup:            ## create venv and install deps (voice models download on first use)
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt
	@command -v ffmpeg >/dev/null || echo "!! ffmpeg not found: install it (apt install ffmpeg / brew install ffmpeg)"
	@command -v espeak-ng >/dev/null || echo "note: espeak-ng not found (optional last-resort TTS)"
	@command -v claude >/dev/null || test -x "$$HOME/.local/bin/claude" || echo "note: Claude Code CLI not found; research/script/plan will use the weak fallback writer (see README)"

setup-chatterbox: ## optional Chatterbox voice in its own venv (pinned torch; setuptools<81 keeps its watermarker working)
	$(PYTHON) -m venv .venv-chatterbox
	.venv-chatterbox/bin/python -m pip install -q --upgrade pip
	.venv-chatterbox/bin/python -m pip install -q "chatterbox-tts==0.1.7" "setuptools<81" soundfile

setup-parler:     ## optional Parler-TTS voice in its own venv
	$(PYTHON) -m venv .venv-parler
	.venv-parler/bin/python -m pip install -q --upgrade pip
	.venv-parler/bin/python -m pip install -q "torch==2.6.0" "torchaudio==2.6.0" "parler-tts==0.2.3" soundfile

plan:             ## only the writer stages (research, script, visual plan): make plan TOPIC="..." [ARGS=--fresh]
	$(PY) -m explainer run "$(TOPIC)" --until plan $(CFGARG) $(ARGS)

voices:           ## compare voices on one paragraph: make voices VOICES=kokoro:af_heart,kokoro:bm_george
	$(PY) -m explainer voices $(if $(VOICES),--try $(VOICES),) $(ARGS)

share:            ## size-capped copy for chat/email: make share VIDEO=out/.../how-gps-works.mp4 MAX_MB=15
	$(PY) -m explainer share "$(VIDEO)" --max-mb $(MAX_MB) $(ARGS)

video:            ## full pipeline: make video TOPIC="how GPS works"
	$(PY) -m explainer run "$(TOPIC)" $(CFGARG) $(ARGS)

vertical:         ## 9:16 render of the whole video
	$(PY) -m explainer run "$(TOPIC)" --config configs/vertical.yaml $(ARGS)

short:            ## short 9:16 render of a few scenes: make short SCENES=hook,signal
	$(PY) -m explainer run "$(TOPIC)" --config configs/vertical.yaml --scenes $(SCENES) --tag short $(ARGS)

stage:            ## re-run one stage: make stage STAGE=music TOPIC="..."
	$(PY) -m explainer stage $(STAGE) "$(TOPIC)" $(CFGARG) --force $(ARGS)

status:
	$(PY) -m explainer status "$(TOPIC)" $(CFGARG) $(ARGS)

preview:          ## still frames per scene for quick layout checks
	$(PY) -m explainer preview "$(TOPIC)" $(CFGARG) $(ARGS)

frames:           ## still frames + contact sheet drawn from the visual plan: make frames TOPIC="..." PER_SCENE=4
	$(PY) -m explainer frames "$(TOPIC)" --per-scene $(PER_SCENE) $(CFGARG) $(ARGS)

clean:
	$(PY) -m explainer clean "$(TOPIC)"

samples:          ## the two sample videos + a short vertical proof
	$(PY) -m explainer run "how GPS works"
	$(PY) -m explainer run "how a heat pump works"
	$(PY) -m explainer run "how GPS works" --config configs/vertical.yaml --scenes hook,signal,trilateration --tag short

test:
	$(PY) -m unittest discover -s tests -v
