"""Engine–game contract for the hybrid build (docs/contract.md, docs/engine-plan.md Appendix B).

Pydantic models shared by the engine packages and the REST API: maps and saved revisions,
run launch, the per-tick game observation and engine outcome, 911 dispatch, mayor decisions
and exceptional orders, the seven disruption types and the political status. They depend only
on `aiautonomy.engines.core`. Their JSON Schema is exported with the WebSocket protocol
(`make protocol`) and drives the generated TypeScript types.

REQ: ARCH-02, ARCH-03
"""
