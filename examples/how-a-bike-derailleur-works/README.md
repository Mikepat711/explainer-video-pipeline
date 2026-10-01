# Visual plan outline: how a bike derailleur shifts gears

A contrast example for the visual plan format. The grid lesson is about invisible quantities spread
over a continent: power, frequency, voltage. This one is a hand-sized machine where every part can be
seen moving. Both are drawn by the same renderer from the same vocabulary, but they share almost no
actors, style or staging. That is the point of writing a plan per lesson instead of filling in templates.

This folder is not a topic pack, so it never overrides Claude for this topic. Draw it with:

```bash
.venv/bin/python -m explainer frames "how a bike derailleur works" \
  --plan examples/how-a-bike-derailleur-works/plan.json \
  --script examples/how-a-bike-derailleur-works/script.md --per-scene 4
```

To render it as a full video, copy `plan.json` and `script.md` into `topics/how-a-bike-derailleur-works/`
and run `make video TOPIC="how a bike derailleur works"`.

## Style

Workshop-manual look: warm paper background, ink linework, a humanist typeface, orange for what is
being pushed and blue for what is being moved. The grid lesson uses a night-time control room
(dark navy, glowing amber energy, cyan instruments). Neither style is a theme preset; each plan sets
its own palette and mood.

## Scenes

### 1. `ratio`: one pedal turn, two distances (side view)

- **Mechanism**: the gear ratio is chainring teeth divided by cog teeth.
- **Actors**: a 50-tooth chainring, 25- and 11-tooth cogs on the hub, a chain wrapped around the
  chainring and the active cog, the rear wheel, and a "wheel turns per pedal" readout.
- **Scale**: gears are drawn to scale, with radius proportional to tooth count. The wheel is shrunk to
  fit and labelled "not to scale".
- **Beats**:
  - Sentence 1: the chainring pulses.
  - Sentence 2: the cog label and the readout appear at 2.0.
  - Sentence 3: the 11-tooth cog pops in and the chain cross-fades onto it. The wheel and cogs speed
    up from 24 to 54.5 visual rpm while the chainring stays at 12, and the readout climbs to 4.5.
  - Sentence 4: the trade-off appears as one line of text.

### 2. `shift`: a cable, a spring and a parallelogram (rear view)

- **Mechanism**: cable tension swings the parallelogram inboard onto bigger cogs and a return spring
  pushes it back. The linkage is slanted, so the jockey wheel's path follows the cone of cogs.
- **Actors**: five cogs edge-on as a stepped cone; two parallel links (levers) sharing one angle; the
  knuckle, cage arm and jockey wheel; a chain segment rising to the active cog; a diagonal return
  spring; the shifter cable; pull and return arrows; a dashed track.
- **Geometry**: each stop puts the jockey wheel under one cog with the chain meeting the cog's bottom
  edge. The link angle for each stop is solved on the links' 290-unit arc, so the knuckle, cage and
  jockey wheel stay attached to the link tips at every stop. Moves go one cog at a time, as indexed
  shifting does, so between stops the parts drift apart by at most 1.6 units (about 2 pixels at
  1080p). The spring runs from one link's pivot to the other link's tip, so it lengthens and shortens
  with the linkage on its own.
- **Beats**:
  - Sentence 1: the cogs pulse.
  - Sentence 2: the parallelogram and jockey wheel labels appear.
  - Sentence 3: the cable tightens twice and the jockey wheel steps two cogs inboard.
  - Sentence 4: the cable relaxes and the spring returns the jockey wheel to the smallest cog, one cog
    at a time.
  - Sentence 5: the dashed track draws in, then a long pull clicks the jockey wheel down the slant
    to the biggest cog.

### 3. `slack`: taking up the slack (side view)

- **Mechanism**: a spring-loaded arm carries the tension pulley. It swings forward to give up chain on a
  big cog and back to take up slack on a small one.
- **Actors**: chainring, cassette (25- and 11-tooth cogs), the cage arm (a lever) with its tension
  pulley, a spring from the frame to the arm, a chain wrapped around chainring, cog and pulley, and an
  "extra chain wrapped" readout.
- **Geometry**: the arm angle on the big cog (61.9°, against 112° on the small cog) was solved so the
  chain loop has the same length in both gears: 2576 units. The arm swings exactly as far as the extra
  wrap requires.
- **Numbers**: going from 11 to 25 teeth wraps about 7 more half-inch pitches, roughly 9 cm. The
  readout counts to 9 cm.
- **Beats**:
  - Sentence 1: the big cog pulses.
  - Sentence 2: the chain cross-fades to the big cog while the arm swings forward, the cogs slow down
    and the readout counts up.
  - Sentence 3: everything reverses.
  - Sentence 4: a closing line appears.

## Grid and derailleur side by side

| | Grid lesson | Derailleur lesson |
|---|---|---|
| Subject | Continent-scale system, invisible quantities | Hand-sized machine, every part visible |
| Main actors | `generator`, `plant`, `network`, `powerline`, `gauge`, `breaker`, `house` | `gear`, `chain`, `lever`, `spring`, `cable`, `shape` |
| What moves | Rotor phase, power flow particles, frequency needle, lights going out | Teeth, chain links, linkage angles, a sliding jockey wheel |
| Readouts | Hz, MW, kV, % load | Wheel turns per pedal, cm of chain |
| Camera | Pans and zooms across a map | Locked off; the mechanism moves instead |
| Honest scale | "Exaggerated for illustration" where one kettle visibly moves the grid | Gears to scale by teeth; the wheel labelled "not to scale" |

## Simplifications

- The side views leave out the upper guide pulley. The chain is drawn as a convex loop around
  chainring, cog and tension pulley, which is what the slack-taking mechanism needs to show.
- The rear view draws the parallelogram as a flat four-bar linkage. On a real derailleur the pivots
  are tilted so the linkage swings in three dimensions, but the motion it produces is the same: inboard
  and down along the cone.
- The pulley and cogs spin at visual speeds within the renderer's 75 rpm strobe limit. The ratios
  between them are kept, not the real rpm.
