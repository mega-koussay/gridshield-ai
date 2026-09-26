# GridShield AI — Pitch Deck (10 slides)

Slide-by-slide content used to build `pitch_deck.pptx`.

---

## Slide 1 — Problem
**The grid's sensors can lie — and operators act on it.**
- Millions of smart meters, inverters and SCADA nodes = millions of entry points
- A false-data injection skews what operators *see*; a hijacked command skews what they *do*
- Energy tools trust all data; security tools don't understand energy
- Result: wrong dispatch, avoidable imports, blackouts — discovered too late

## Slide 2 — Solution
**GridShield AI: predict, protect, optimize — through attacks.**
- Live digital twin of a solar+battery campus microgrid
- AI detects when data lies, explains why, isolates the traitor device
- Keeps operating on reconstructed trusted values
- Re-optimizes the battery in seconds — resilience, not just alerts

## Slide 3 — How it works / architecture
- Twin: deterministic physics at 5-min steps (solar, battery, grid, 6 buildings, smart meters, SCADA)
- AI: forecasters → 5-channel hybrid detector → classifier → explanations
- Response: isolate → reconstruct → MPC re-solve → audit log → re-admit
- FastAPI + WebSocket backend, React dashboard; runs on a laptop
*(architecture diagram: docs/diagrams/architecture.svg)*

## Slide 4 — Digital twin
**Two data planes — the core trick.**
- RAW plane = exactly what SCADA sees (attacked)
- TRUSTED plane = what the AI controls with
- Attacks corrupt the view, never the physics — like real FDI
- Twin + attacks + detection in one loop = measurable resilience
*(data-flow diagram: docs/diagrams/data-flow.svg)*

## Slide 5 — AI
- Forecast: solar 10.3 kW / demand 7.1 kW MAE (1 h, laptop-trained in <1 s)
- Detect: 5 evidence channels incl. control-plane consistency — battery must obey *the defender's* plan
- Calibrated threshold = P99.5 of clean traffic → **0.5% false positives by construction**
- Measured: precision 1.00, first alert in 1 step, 5/5 attack classes

## Slide 6 — Cyber defense (the live demo)
- One click: FDI_BULK launches, metered load jumps +35%
- Phase tracker: ATTACK → DETECTION → EXPLANATION → DEFENSE → RECONSTRUCTION → RE-OPTIMIZATION → RECOVERY
- Jury-readable explanation: reasons, evidence, threshold, attributions
- Same seed ⇒ identical run, every time

## Slide 7 — Results (measured, not invented)
- Detection: precision 1.00 / FPR 0.5% / latency 1 step (all 5 classes)
- Response: hijack exposure 25 → **5 min**; battery deviation **−80%**
- Federated FedAvg: global MAE 7.06 kW = centralized 7.06 kW, zero raw data shared
- 29 backend + 5 frontend tests green; every number reproducible via `scripts/run_experiments.py`

## Slide 8 — Impact & scalability
- Target users: campuses, distribution operators, industrial parks
- Value: minutes of corrupted decisions avoided; battery assets protected; audit trail for regulators
- Deploy: twin contract ↔ real historian feed; per-feeder detectors; ms-level compute per tick
- Societal: a template for automation that explains itself in critical infrastructure

## Slide 9 — Innovation & bonus areas
- **Digital twin** with two data planes (✓ bonus)
- **Explainable AI** on every alert (✓ bonus)
- **Live cyberattack demo** on a local simulation (✓ bonus)
- **Federated learning** FedAvg PoC — weights only (✓ bonus)
- Control-plane detection channel — catches attacks telemetry-only detectors miss
- Honest evaluation: no invented numbers, no fake buttons

## Slide 10 — Conclusion & roadmap
**GridShield AI makes renewable microgrids trustworthy under attack.**
- Next: real SCADA ingestion (IEC 61850), probabilistic forecasts, SHAP in production, federated detection, hardware-in-the-loop
- The detect→explain→contain→reconstruct→optimize loop is ready today
- **Predict. Protect. Optimize.**
