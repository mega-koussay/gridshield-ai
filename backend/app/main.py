"""GridShield AI — FastAPI application.

REST + WebSocket API over the live orchestrator. Run with:

    uvicorn app.main:app --host 127.0.0.1 --port 8000   (from backend/)

or `python -m app.main` for a direct start.
"""
from __future__ import annotations

import asyncio
import json
import logging
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.eventstore import event_store
from app.services.orchestrator import orchestrator
from app.twin.attacks import ATTACK_TYPES

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger("gridshield")

CREATE_ROOT = Path(__file__).resolve().parents[2]  # repo root


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_store.record_event({
        "kind": "SYSTEM", "severity": "info",
        "message": "GridShield AI backend started.",
    })
    await hub.start()  # live 1 Hz broadcast loop (must start WITH the app)
    logger.info("GridShield AI ready (seed=%s)", settings.seed)
    yield
    if hub.task is not None:
        hub.task.cancel()
    event_store.record_event({
        "kind": "SYSTEM", "severity": "info",
        "message": "GridShield AI backend stopped.",
    })


app = FastAPI(title="GridShield AI API", version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local PoC; the dashboard runs on localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------- #
class AttackRequest(BaseModel):
    attack_type: str = Field(..., description=f"One of {', '.join(ATTACK_TYPES)}")
    device_id: Optional[str] = None
    duration_min: int = Field(30, ge=1, le=240)
    magnitude: Optional[float] = None
    delay_min: int = Field(0, ge=0, le=60)


class DemoRequest(BaseModel):
    seed: Optional[int] = None
    attack_type: str = "FDI_BULK"
    delay_min: int = Field(0, ge=0, le=60)
    magnitude: Optional[float] = None


class SetpointRequest(BaseModel):
    battery_kw: float = Field(..., description="Battery power setpoint [-200, 200]")


# --------------------------------------------------------------------- #
# Health / status
# --------------------------------------------------------------------- #
@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "name": settings.app_name,
        "tagline": settings.tagline,
        "version": settings.version,
        "docs": "/docs",
        "ws": "/ws/live",
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    h = orchestrator.health()
    h["db_ok"] = True
    try:
        event_store.recent_events(1)
    except Exception:
        h["db_ok"] = False
    return h


@app.get("/api/state/current")
async def current_state() -> Dict[str, Any]:
    if orchestrator.last_payload is None:
        orchestrator.step()
    return orchestrator.last_payload


# --------------------------------------------------------------------- #
# Simulation control
# --------------------------------------------------------------------- #
@app.post("/api/sim/step")
async def sim_step() -> Dict[str, Any]:
    return orchestrator.step()


@app.post("/api/sim/reset")
async def sim_reset(seed: Optional[int] = None) -> Dict[str, Any]:
    orchestrator.reset(seed=seed)
    return orchestrator.step()


@app.post("/api/sim/scada-setpoint")
async def scada_setpoint(req: SetpointRequest) -> Dict[str, Any]:
    """Operator override of the battery setpoint (the defender's handle)."""
    p = float(max(-settings.battery_power_kw, min(settings.battery_power_kw, req.battery_kw)))
    orchestrator.sim.battery_setpoint_kw = p
    return {"ok": True, "setpoint_kw": p}


# --------------------------------------------------------------------- #
# Attacks
# --------------------------------------------------------------------- #
@app.post("/api/attack/launch")
async def attack_launch(req: AttackRequest) -> Dict[str, Any]:
    if req.attack_type not in ATTACK_TYPES:
        raise HTTPException(400, f"attack_type must be one of {ATTACK_TYPES}")
    dev = req.device_id or (
        "MTR_B1_Offices" if req.attack_type in ("FDI_BULK", "DEVICE_MALWARE")
        else "MTR_SOLAR" if req.attack_type in ("FDI_SOLAR", "TELEMETRY_SPIKE")
        else "SCADA_ESS"
    )
    ev = orchestrator.attacks.launch(
        req.attack_type, dev,
        duration_min=req.duration_min,
        magnitude=req.magnitude,
        current_step=orchestrator.sim.step_index + max(0, int(req.delay_min / settings.step_minutes)),
    )
    event_store.record_event({
        "kind": "ATTACK", "severity": "critical",
        "message": f"Manual attack launched: {ev.attack_type} on {ev.device_id}",
        "extra": {"attack_id": ev.attack_id},
    })
    return {"ok": True, "attack": ev.to_dict()}


@app.get("/api/attack/status")
async def attack_status() -> Dict[str, Any]:
    return orchestrator.attacks.status()


# --------------------------------------------------------------------- #
# Deterministic demo scenario
# --------------------------------------------------------------------- #
@app.post("/api/demo/launch")
async def demo_launch(req: DemoRequest) -> Dict[str, Any]:
    payload = orchestrator.launch_demo(
        seed=req.seed, attack_type=req.attack_type,
        delay_min=req.delay_min, magnitude=req.magnitude,
    )
    event_store.record_event({
        "kind": "DEMO", "severity": "info",
        "message": f"Deterministic demo armed (seed={req.seed or settings.scenario_seed}, "
                   f"attack={req.attack_type}).",
    })
    return payload


@app.post("/api/demo/reset")
async def demo_reset() -> Dict[str, Any]:
    orchestrator.reset(seed=settings.scenario_seed)
    return orchestrator.step()


# --------------------------------------------------------------------- #
# Devices / incidents / history
# --------------------------------------------------------------------- #
@app.get("/api/devices")
async def devices() -> List[Dict[str, Any]]:
    return [d.to_dict() for d in orchestrator.sim.devices]


@app.get("/api/incidents")
async def incidents() -> Dict[str, Any]:
    return orchestrator.responder.status()


@app.get("/api/incidents/history")
async def incident_history(limit: int = 50) -> List[Dict[str, Any]]:
    return event_store.incident_history(limit)


@app.get("/api/events/recent")
async def recent_events(limit: int = 100) -> List[Dict[str, Any]]:
    return event_store.recent_events(limit)


# --------------------------------------------------------------------- #
# Models / metrics / federated
# --------------------------------------------------------------------- #
@app.get("/api/models/status")
async def models_status() -> Dict[str, Any]:
    return orchestrator.health()["models"]


@app.get("/api/fl/status")
async def fl_status() -> Dict[str, Any]:
    """Federated-learning summary (runs the seeded FedAvg simulation)."""
    from app.ai.federated import run_federated
    df = orchestrator._load_dataset()
    if df is None:
        raise HTTPException(503, "Dataset not available")
    clean = df[df["label"] == 0]
    res = run_federated(clean.head(2000))
    return res


# --------------------------------------------------------------------- #
# WebSocket live stream
# --------------------------------------------------------------------- #
# NOTE: `hub` is defined here, AFTER all route handlers that reference it
# (Python resolves the name at call time), but BEFORE lifespan runs.
class LiveHub:
    """Broadcasts orchestrator payloads to all connected dashboards."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.task: Optional[asyncio.Task] = None

    async def _loop(self) -> None:
        while True:
            try:
                payload = await asyncio.to_thread(orchestrator.step)
            except Exception as exc:  # keep the stream alive
                logger.exception("orchestrator.step failed: %s", exc)
                payload = {"error": str(exc)}
            dead: List[WebSocket] = []
            data = json.dumps(payload, default=str)
            for ws in list(self.clients):
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)
            await asyncio.sleep(settings.tick_seconds)

    async def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())


hub = LiveHub()


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await ws.accept()
    hub.clients.add(ws)
    try:
        if orchestrator.last_payload is None:
            await ws.send_text(json.dumps(await asyncio.to_thread(orchestrator.step), default=str))
        while True:
            # Keep the connection alive; client may send control pings.
            msg = await ws.receive_text()
            if msg == "step":
                await asyncio.to_thread(orchestrator.step)
            elif msg == "reset":
                await asyncio.to_thread(orchestrator.reset)
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
