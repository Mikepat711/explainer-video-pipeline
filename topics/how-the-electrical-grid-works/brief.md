---
config:
  length:
    target_seconds: 240   # room for six required topics on top of the core lesson (~560 words of narration)
    max_seconds: 300
---
# Brief: how the electrical grid works

<!--
Producer's brief for the Claude writer, read automatically for this topic. To have Claude write a new research
brief, script and visual plan that must cover every required topic below (instead of using the pinned
research.md / script.md / plan.json in this folder):

    make plan TOPIC="how the electrical grid works" ARGS="--fresh"

Everything outside "Required topics" (except this comment and the title) is passed to the writer as notes.
-->

## Required topics
- thermal: Thermal plants: gas, coal and nuclear stations all turn heat into spinning motion. Coal and nuclear boil water into high-pressure steam that spins a turbine; gas plants burn fuel in a combustion turbine and, in combined-cycle plants, reuse its hot exhaust to raise steam for a second turbine. The steam cycles differ only in their heat source (burning coal, fission, hot gas-turbine exhaust), so show the shared heat, steam, turbine and generator chain and which heat source feeds it.
- hydro: Hydroelectric plants: water held behind a dam falls through a penstock and spins a turbine; opening or closing the gates ramps output up or down within minutes.
- wind: Wind turbines: moving air turns the blades, and the rotor drives a generator in the nacelle; output climbs steeply with wind speed and stops in calm air or storms, and power electronics connect the turbine to the grid.
- solar: Solar photovoltaic: panels turn sunlight directly into direct current with no turbine and no moving parts; inverters convert it to grid AC; output follows the sun and dips as clouds pass.
- line-faults: Line faults and protection: a fault (a tree or lightning strike, a failed insulator) makes current surge; protective relays detect it within a few cycles and trip circuit breakers that isolate only the faulted section; automatic reclosing tests whether the fault has cleared, and power reroutes around the gap.
- black-start: Blackouts, black start and restoration: when protection cannot contain a disturbance, cascading trips can black out a whole region. Restoration starts from black-start units (often hydro or small gas or diesel units that can start without grid power), which energize lines step by step and start the larger plants; operators reconnect customers in blocks so frequency stays near 60 Hz, then resynchronize the islands into one grid.

## Notes
This is a rewrite of the lesson. Keep its spine: the grid stores almost nothing, so supply must match demand every instant, and frequency is the shared signal that shows whether they balance. Load-shedding on its own is not the outage story; protection tripping a faulted line and black-start restoration after a blackout are.

Each plant type needs a visual that looks and moves differently from the others (a steam turbine hall with its heat source, a dam with falling water, turning rotor blades, flat panels with no moving parts), never the same icon relabelled.

Honest scale: label every magnified effect, and make those notes as legible as any other label.
