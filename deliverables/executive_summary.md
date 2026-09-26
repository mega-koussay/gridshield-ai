# GridShield AI — Executive Summary

**Predict. Protect. Optimize.**
IEEE SmartSecureGrid Challenge 2026 — Proof of Concept

---

## The problem

Modern power grids are becoming millions of interconnected cyber-physical
devices: solar inverters, batteries, smart meters, SCADA controllers. Every
device that can be *measured remotely* can also be **lied to**. A false-data
injection that inflates consumption, a spoofed solar reading, or one hijacked
battery command can cause wrong decisions — charging at the wrong time,
importing expensive energy, or blacking out a building — long before any
human operator notices.

Utilities and campus operators today have two disconnected worlds: energy
management systems that *optimize* but trust all data, and security tools
that *alert* but do not understand energy. The missing piece is a system that
does both, in real time, and explains itself.

## Target users

- **Distribution & campus operators** (universities, hospitals, industrial
  parks, utilities with renewables and storage) who need to keep operating
  through bad data, not just be told about it.
- **Security operations teams** who need energy-aware anomaly detection with
  explanations they can act on.

## The solution

**GridShield AI** is a working PoC: a live digital twin of a solar + battery
microgrid with six buildings, on top of which an AI layer runs a continuous
loop:

```
NORMAL → ATTACK → AI DETECTION → EXPLANATION → AUTOMATIC DEFENSE
       → RECONSTRUCTION → RE-OPTIMIZATION → RECOVERY
```

- **Predict** — lightweight, laptop-friendly forecasters anticipate solar
  production and demand one hour ahead (measured MAE ≈ 7 kW demand,
  ≈ 10 kW solar on 250 kW plant / ~230 kW peak campus).
- **Protect** — a hybrid detector fuses five evidence channels (load residual,
  solar residual, per-meter disagreement, isolation-forest, and a
  *control-plane consistency* channel that catches hijacked SCADA commands).
  The alert threshold is calibrated at the 99.5th percentile of clean traffic,
  so the false-positive rate is ~0.5% by construction — measured 0.5%.
- **Optimize** — an exact dynamic-programming planner + receding-horizon MPC
  schedules the battery on *trusted* data; after an attack it re-solves within
  seconds on reconstructed values.

## What happens when attacked

When the detector fires (measured detection latency: **the first 5-minute
step**), GridShield AI: identifies the likely compromised device with a
confidence score, **isolates it**, revokes its control session, **reconstructs
the missing data** from trusted AI forecasts and healthy neighbors, re-optimizes
the battery plan, and logs every action in an auditable incident timeline.
After eight consecutive clean steps the device is re-admitted.

**Measured before/after (same attack, same seed):** battery hijack exposure
cut from **25 to 5 minutes**, battery deviation from the intended plan reduced
by **80%**, and total effective energy cost reduced. Every attack class in the
suite (5/5) is detected, explained, contained, and recovered in the
deterministic scenario.

## Innovation & bonus areas

1. **Digital twin with two data planes**: the twin keeps *true physics*
   separate from *what SCADA sees* — the same false-data illusion operators
   face, reproduced safely (Digital Twin ✓).
2. **Control-plane detection channel**: most published FDI detectors watch
   measurements; GridShield also verifies the battery *obeys the defender's
   setpoint*, which catches control-command attacks that look harmless in
   telemetry (Live cyberattack demonstration ✓).
3. **Explainable alerts**: every alert carries human-readable reasons,
   channel evidence, threshold calibration, and feature attributions
   (Explainable AI ✓).
4. **Federated learning PoC**: six buildings train demand models locally and
   exchange only model weights (FedAvg) — converging to the centralized
   baseline without sharing consumption data (Federated Learning ✓).
5. **Honest numbers**: every figure in this PoC is produced by
   `scripts/run_experiments.py` on the shipped dataset; no invented results.

## Technology stack

Python 3.13 + FastAPI + WebSockets (backend), React + TypeScript + Recharts
(dashboard), NumPy/pandas/scikit-learn (AI), SQLite (audit trail), Docker
(deployment). One command per terminal to start; runs on any student laptop.

## Scalability & impact

The architecture is deliberately modular: the twin is replaceable by a real
SCADA/AMS feed (same data contract), detectors run per-feeder, and the
federated layer scales to more buildings without new data flows. For a campus
operator, the value is direct: fewer minutes of decisions made on corrupted
data, fewer avoidable imports, battery assets protected from hostile commands,
and a defensible audit trail for every automated action.

## Conclusion

GridShield AI demonstrates — live, reproducibly, and with measured results —
that AI can make a renewable microgrid not just smarter, but **trustworthy
under attack**: predicting what should happen, detecting when the data lies,
explaining why, defending automatically, and optimizing through the incident.
