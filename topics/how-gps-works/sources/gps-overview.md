# GPS overview (hand-written summary notes)

Reading list used to write these notes: gps.gov "GPS: The Space Segment" and "GPS Accuracy" pages,
the Navstar GPS Interface Specification IS-GPS-200 (public), and standard GNSS textbooks.

The Global Positioning System is a satellite navigation system operated by the United States Space Force.
The baseline constellation needs 24 satellites, and typically about 31 operational satellites are in orbit.
GPS satellites fly in medium Earth orbit at an altitude of approximately 20,200 kilometers.
Each satellite circles the Earth twice a day, completing one orbit in roughly 11 hours and 58 minutes.
The satellites are arranged in six equally spaced orbital planes inclined at about 55 degrees to the equator.
This arrangement ensures that at least four satellites are visible from virtually any point on Earth.

Each satellite carries several atomic clocks, based on rubidium or cesium, which keep extremely stable time.
Each satellite continuously broadcasts a navigation message on radio frequencies such as L1 at 1575.42 MHz.
The navigation message contains the satellite identity, its precise orbit (the ephemeris), and the time of transmission.
A GPS receiver is passive: it only listens and never transmits anything to the satellites.
Radio signals travel at the speed of light, about 299,792 kilometers per second.
By comparing the transmit time with the arrival time, the receiver computes a travel time of around 67 to 86 milliseconds.
Multiplying the travel time by the speed of light gives the distance to that satellite, called a pseudorange.

One distance places the receiver somewhere on a sphere centered on the satellite.
Two spheres intersect in a circle, and three spheres intersect in two points, one of which is usually far from Earth.
This geometric process is called trilateration.
The receiver clock is an inexpensive quartz oscillator and is not synchronized with the satellites.
Light travels about 300 kilometers in one millisecond, so a one millisecond clock error would cause a 300 kilometer error.
The receiver therefore treats its own clock error as a fourth unknown, alongside latitude, longitude and altitude.
Solving for four unknowns requires measurements from at least four satellites.

Relativity affects the satellite clocks. Because of their orbital speed, special relativity makes them run slower by about 7 microseconds per day.
Because they sit higher in Earth's gravity well, general relativity makes them run faster by about 45 microseconds per day.
The net effect is that satellite clocks gain about 38 microseconds per day relative to clocks on the ground.
Without correction, this would accumulate into position errors of roughly 10 kilometers per day.
The satellite clock frequency is deliberately offset before launch to compensate.

Remaining error sources include ionospheric delay, tropospheric delay, multipath reflections from buildings, and orbit and clock errors.
The ionosphere slows radio signals by an amount that depends on frequency, so dual-frequency receivers can measure and remove it.
Modern receivers also use other constellations such as Galileo, GLONASS and BeiDou.
Augmentation systems such as WAAS and RTK corrections from ground stations can improve accuracy to centimeters.
A typical smartphone achieves an accuracy of roughly 5 meters under open sky.
