# GridShield AI

**Predict. Protect. Optimize.**

AI-powered cybersecurity & resilience platform for a simulated renewable-energy
microgrid — IEEE SmartSecureGrid Challenge 2026 Proof of Concept.

GridShield AI combines a **live digital twin** of a solar+battery campus
microgrid, **short-horizon AI forecasting**, **hybrid anomaly detection**,
**explainable alerts**, **automatic containment & self-healing**, and
**battery/load optimization** — plus a **federated-learning PoC** where
buildings train locally and share only model weights.

```
NORMAL → ATTACK → AI DETECTION → EXPLANATION → AUTOMATIC DEFENSE
       → RECONSTRUCTION → RE-OPTIMIZATION → RECOVERY
```

---

## Quick start

### Windows — the easy way
Double-click **`START_HERE.bat`** (in the project root). It opens both
windows and the dashboard in your browser. Done.

(The two individual launchers `start_backend.bat` and `start_frontend.bat`
also work, and double as clean PowerShell examples: the venv lives in the
project root, so paths like `.venv\Scripts\uvicorn.exe` must be run from
there — never `cd backend` first.)

### Prerequisites (fresh machines)
- Python 3.11+ (3.13 tested) and Node.js 18+ (24 tested)
- No GPU, no external data, no internet needed at runtime.

### Manual setup (any OS)

Windows (PowerShell, from the project root):
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
npm install --prefix frontend

# Terminal 1 - backend (run from project root):
.venv\Scripts\uvicorn.exe app.main:app --port 8000 --app-dir backend

# Terminal 2 - dashboard:
npm run dev --prefix frontend
```

Linux / macOS (from the project root):
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install --prefix frontend

.venv/bin/uvicorn app.main:app --port 8000 --app-dir backend   # terminal 1
npm run dev --prefix frontend                                   # terminal 2
```

On first start the backend trains its models from the shipped dataset
(~40 s, one time) and prints `GridShield AI ready`.

Open <http://localhost:5173> — the dashboard connects over WebSocket and
updates every second.
Health check: <http://127.0.0.1:8000/health> · API docs: <http://127.0.0.1:8000/docs>

### Docker alternative
```bash
docker compose up --build
# dashboard: http://localhost:5173   API: http://localhost:8000
```

---

## The 60-second demo

1. Press **▶ RUN DEMO** (default attack `FDI_BULK`, seed `2026`).
2. Watch the phase tracker: `NORMAL → ATTACK → DETECTION → EXPLANATION →
   DEFENSE → RECONSTRUCTION → RE-OPTIMIZATION → RECOVERY`.
3. The **AI explanation panel** shows *why* the alert fired (channels,
   thresholds, attributions) while the compromised meter is **isolated**.
4. The twin keeps operating on **trusted reconstructed values**; the battery
   plan is re-optimized; the device is re-admitted after a clean probation.
5. **⟲ RESET** returns everything to a deterministic starting state.
   Same seed ⇒ identical scenario, every time.

You can also launch any of the five attack classes individually
(`FDI_BULK`, `FDI_SOLAR`, `SCADA_CMD`, `DEVICE_MALWARE`, `TELEMETRY_SPIKE`).

> ⚠️ The attack simulator only corrupts telemetry **inside this local
> simulation**. It never touches real networks or third-party systems.

---

## What's inside

```
├─ backend/
│  ├─ app/
│  │  ├─ core/config.py         # seeded, env-driven configuration
│  │  ├─ twin/simulator.py      # deterministic microgrid digital twin
│  │  ├─ twin/attacks.py        # 5 attack classes (telemetry/control injection)
│  │  ├─ ai/forecast.py         # Ridge forecasters (solar + demand)
│  │  ├─ ai/anomaly.py          # hybrid detector (z-scores + iForest + control-plane)
│  │  ├─ ai/classifier.py       # RandomForest attack-type identification
│  │  ├─ ai/explain.py          # jury-readable explanations + attributions
│  │  ├─ ai/optimizer.py        # DP day-ahead planner + receding-horizon MPC
│  │  ├─ ai/reconstruction.py   # trusted-value reconstruction (channel-aware)
│  │  ├─ ai/federated.py        # FedAvg federated-learning PoC
│  │  ├─ services/orchestrator.py  # live control loop + demo state machine
│  │  ├─ services/eventstore.py    # SQLite incident/event persistence
│  │  └─ main.py                # FastAPI REST + WebSocket API
│  ├─ data/microgrid_dataset.csv   # 6,000 labeled steps (5-min resolution)
│  ├─ models/                      # saved model artifacts (auto-generated)
│  └─ reports/                     # metrics.json + evaluation figures
├─ frontend/                    # React + TypeScript + Recharts dashboard
├─ scripts/
│  ├─ generate_dataset.py       # regenerate the labeled dataset
│  └─ run_experiments.py        # reproduce every reported metric & figure
├─ tests/                       # 29 pytest tests (unit + integration + API)
├─ docs/                        # diagrams, storyboard, references
├─ deliverables/                # executive summary, technical report, pitch deck
├─ docker-compose.yml, backend/Dockerfile, frontend/Dockerfile
└─ requirements.txt / .env.example
```

## Configuration

Copy `.env.example` to `.env` to tweak seeds, sizes and clock speed.
Everything runs on fixed seeds: `GRIDSHIELD_SEED` drives the world,
`GRIDSHIELD_SCENARIO_SEED` the demo episode.

## Reproducing the results

```bash
python scripts/generate_dataset.py           # dataset (6,000 steps, labeled)
python scripts/run_experiments.py            # metrics.json + figures
pytest tests/ -q                             # 29 backend tests
cd frontend && npm test                      # 5 frontend tests
```

All reported numbers in the technical report come from `backend/reports/metrics.json`.

## API map

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness + model status |
| `GET /api/state/current` | last full telemetry payload |
| `POST /api/sim/step` `/api/sim/reset` | manual stepping |
| `POST /api/attack/launch` | inject one of the 5 attack classes |
| `POST /api/demo/launch` `/api/demo/reset` | deterministic one-click scenario |
| `GET /api/devices` `/api/incidents` `/api/incidents/history` | security state |
| `GET /api/fl/status` | federated-learning results |
| `WS /ws/live` | 1 Hz full-state stream for dashboards |

## Known limitations

- Synthetic world: physics are stylized (power-balance + SOC dynamics), not
  a full AC power-flow solver.
- Detection is supervised by clean-data calibration; slow (sub-σ) FDI
  biasing below the noise floor is out of scope for the live demo.
- Federated learning simulates 6 participants on split data; it is a working
  FedAvg PoC, not a distributed deployment.
- Forecasters are linear by design (fast, interpretable, laptop-friendly).

See `deliverables/technical_report` for the full discussion.
