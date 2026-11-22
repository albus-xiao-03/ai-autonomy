---
name: add-event
description: Add or change a city event (protest, flood, blizzard, fire, corruption scandal) so it affects the city, traffic, the mayor, and the satisfaction score. Use for any new disaster or protest work.
---

# Add an event

Define the event first (catalog: `game/incidents.js` `types`; requirements: `SPEC.md` Section 9):

- id and display name
- trigger (scripted time, location, or manual button)
- location and radius (district or landmark)
- duration and intensity
- effects on: roads (closures), buildings (damage), traffic (speed, rerouting), services demand (police, fire, EMS, hospitals), resident behavior (routine vs autonomous residents), satisfaction score
- what the mayor can do about it (which actions help)

Then implement and check:

1. Event fires from the Trigger Event panel (presenter can fire it live).
2. Visible effect on the map (closure marker, color change, particles).
3. Traffic reroutes around closures; no cars stuck on closed roads.
4. The satisfaction score visibly drops, and recovers when the mayor handles it.
5. The event appears in the mayor's state summary so it can respond.
6. Run `verify-game`.
