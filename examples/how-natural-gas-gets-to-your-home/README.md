# How Natural Gas Gets to Your Home

Example **project bundle** for `explainer build`. The directory holds the authored
lesson — script data, scene and art code, and a manifest — not rendered media.
Shared drawing helpers (`lib`, `art`, `art_pro`) live in the pipeline package.

```bash
# after `make setup-bundle`
.venv/bin/explainer build examples/how-natural-gas-gets-to-your-home
# -> out/how-natural-gas-gets-to-your-home/16x9/how-natural-gas-gets-to-your-home.mp4
```

- **Voice:** Kokoro `af_heart` at speed 0.97 (or `--voice elevenlabs:max` / `elevenlabs:todd`)
- **Picture:** 1920×1080 @ 30 fps, dark navy, burned-in rounded captions
- **Length:** about 13 scenes, ~4 minutes of narration

See [docs/bundle.md](../../docs/bundle.md) for the bundle schema.
