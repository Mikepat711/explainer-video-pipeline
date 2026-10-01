---
title: How GPS Works
subtitle: Turning time into position
---

## [hook] Clocks in space
Your phone can find itself to within a few meters, almost anywhere on Earth. And it never sends a single signal to do it. The secret is simple: it listens to clocks in space.

## [constellation] The constellation
GPS is a constellation of about thirty-one satellites, orbiting twenty thousand kilometers up. They circle the planet twice a day, in six tilted orbital planes. That spacing means at least four satellites are above the horizon from almost anywhere.

## [signal] Time of flight
Each satellite carries atomic clocks, and constantly broadcasts who it is, where it is, and exactly when the message left. Your receiver notes when it arrives. Radio travels at the speed of light, so that tiny delay is a distance. About sixty-seven milliseconds means twenty thousand kilometers.

## [trilateration] Trilateration
One distance puts you somewhere on a giant sphere around that satellite. A second satellite narrows it down to a circle. A third leaves just two points, and one of them is out in space. That's trilateration.

## [clock] The fourth satellite
But there's a catch. Your phone's clock is cheap quartz, and light covers three hundred kilometers in a single millisecond. So the receiver adds a fourth satellite, and solves for four unknowns: latitude, longitude, altitude, and its own clock error.

## [relativity] Einstein's correction
Even the satellite clocks need help. Moving fast, they tick slower. Higher up, in weaker gravity, they tick faster. The net gain is about thirty-eight microseconds per day, enough to drift around ten kilometers daily if nobody corrected it.

## [errors] Real-world errors
Then there's the journey itself. The ionosphere slows the signal down, the lower atmosphere bends it, and buildings bounce it around. Modern receivers fight back with two frequencies, extra constellations like Galileo, and corrections from the ground.

## [recap] Recap
So GPS is really a timing system. Precise clocks in orbit, signals at light speed, and a little geometry, turning time into position.
