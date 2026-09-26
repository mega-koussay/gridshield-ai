# GridShield AI — 5-Minute Demo Storyboard (video checklist)

> The video itself is recorded by the user. This is the shot list.
> Deterministic seed `2026` ⇒ every take is identical. Rehearse once, record twice.

## Pre-flight (before recording)
- [ ] Backend running (`uvicorn app.main:app --port 8000`), `/health` shows `"status":"ok"`, all models `true`.
- [ ] Dashboard open at `http://localhost:5173`, badge shows **● LIVE**.
- [ ] Reset once (⟲ RESET) so the run starts from the deterministic warm state.
- [ ] Browser zoom ~90% so twin + charts + panels are all visible.
- [ ] Close Slack/mail notifications. :-)

## Shot list

| # | Time | Screen / action | Say (voice-over cue) |
|---|------|-----------------|----------------------|
| 1 | 0:00–0:20 | Full dashboard, steady state | "GridShield AI — a live digital twin of a solar-and-storage campus microgrid. Solar, battery, grid and six buildings update every second." |
| 2 | 0:20–0:40 | Point at KPI bar + twin flows | "All KPIs are live: energy balance, SOC, self-sufficiency. The twin computes physics; smart meters report it — and that distinction matters." |
| 3 | 0:40–0:55 | Select `FDI_BULK`, show seed 2026 | "We launch a false-data-injection attack: a smart meter starts inflating site demand by ~35%. Note the seed — this run is exactly reproducible." |
| 4 | 0:55–1:15 | Press **▶ RUN DEMO**; phase tracker lights NORMAL→ATTACK | "The attack corrupts what SCADA sees, not physics. The reported load jumps to ~320 kW." |
| 5 | 1:15–1:35 | Phase DETECTION + EXPLANATION; anomaly chart spikes over threshold | "One 5-minute step later the AI flags it. Not just a score: the panel explains — deviation from forecast, per-meter disagreement, physical implausibility — with confidence and calibrated threshold." |
| 6 | 1:35–1:55 | Phase DEFENSE; device list shows ISOLATED; twin shows 'isolated — AI value' | "Automatic containment: the compromised meter is isolated and the attacker's control session revoked. Its data is no longer trusted." |
| 7 | 1:55–2:20 | Phase RECONSTRUCTION; explanation shows trusted values | "GridShield rebuilds the missing values from AI forecasts trained on clean data — operation continues on trusted data." |
| 8 | 2:20–2:45 | Phase RE-OPTIMIZATION; battery plan visibly changes | "The MPC re-solves the battery schedule on the trusted values — resilience, not just detection." |
| 9 | 2:45–3:10 | Phase RECOVERY; status RECOVERED, incident timeline shows full chain | "Eight clean steps later the device is re-admitted. The incident log records every action — auditable by design." |
| 10 | 3:10–3:40 | Show **SCADA_CMD** in dropdown, run again (same seed) | "A nastier attack: a hijacked SCADA session commands the battery itself. Detection uses a control-plane consistency channel — the battery isn't following the defender's plan." |
| 11 | 3:40–4:05 | Point at measured results (report page or metrics.json) | "Measured: hijack exposure cut from 25 minutes to 5, battery deviation down 80% — same seed, reproducible." |
| 12 | 4:05–4:35 | Flip to federated-learning endpoint/figure | "Bonus: six buildings train demand models locally and share only weights — FedAvg converges to the centralized baseline. Privacy by architecture." |
| 13 | 4:35–5:00 | ⟲ RESET, wide shot | "Everything resets to a deterministic state. Predict. Protect. Optimize. — GridShield AI." |

## Backup shots (if time allows)
- Show `/docs` (OpenAPI) briefly for the "real backend" credibility.
- Show `pytest: 29 passed` terminal output for engineering rigor.
- Show `docs/diagrams/architecture.svg` for 5 seconds over the closing line.

## Recording tips
- 1920×1080, 30 fps, dark room theme matches dashboard.
- Record audio separately; the dashboard updates 1×/s — don't rush.
- If anything breaks on take N: reset, same seed, identical take N+1.
