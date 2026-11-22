---
name: verify-game
description: Run the game, take screenshots, compare to the intent in SPEC.md and the Boston reference map, score it, and fix the top gaps. Use after any visual or gameplay change and before saying a task is done.
---

# Verify game (vision loop)

1. Start Ollama, the engine (`uv run aia serve`, port 8787) and the game (port 8712); see README "Run locally". The Events tab must say "Engine online".
2. Render it in a headless browser and save a screenshot (for example with Playwright or headless Chrome).
3. Perform the functional checks that relate to the change. Examples: place a road (curve and drag), place a building, run a day, watch cars follow lanes and lights, trigger an event, open the mayor thought bubble.
4. View the screenshot yourself. Never grade without looking at it.
5. Score 0 to 10 on: matches SPEC.md intent, matches Boston reference map, readability (HUD, tool tabs), low-poly style, no visual bugs (overlapping roads, floating cars, square-block land).
6. List the top 3 gaps. Fix them. Repeat from step 2 until the score is 7 or higher and the functional checks pass.
7. Report what you verified and how. Update `SPEC.md` Section 12.
8. Close the servers you opened (8712, 8787) and unload models (`ollama stop qwen3:8b`, `ollama stop qwen3:1.7b`).
