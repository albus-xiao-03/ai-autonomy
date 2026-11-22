---
name: spec-audit
description: Audit the repo against SPEC.md and report what is done, partial, missing, or unverified. Use before starting new work, after a long session, or when claims need fact-checking.
---

# Spec audit

Goal: an honest status report. Do NOT fix anything during an audit.

1. Read `SPEC.md` Part A fully (Part B only if auditing the Python engine).
2. For every requirement in Sections 3 to 10, find evidence in the code (file and function) and, where possible, check it by running the game.
3. Classify each as: `done (verified)`, `done (unverified)`, `partial`, `missing`, or `conflicts with a hard rule`.
4. Check every Section 2 hard rule explicitly (branch, push only on user confirmation, mayor brain options with cloud off by default, residents local-only, labeled fallback, free placement, non-square land, palette present, seamless roads, landmarks fixed, ports).
5. Compare README claims to what the code and tests actually show. Flag any claim you cannot verify.
6. Update the Status table in `SPEC.md` Section 12 (12b for engine milestones) to match reality.
7. Output: a table (requirement, status, evidence) and the top 5 gaps ranked by impact on the Sundai demo.
