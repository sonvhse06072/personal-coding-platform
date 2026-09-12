from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from .config import clear_config_cache, get_config
from .schemas import (
    ReassessRequest,
    ReassessResponse,
    RoutingRequest,
    RoutingResponse,
    StaffingRequest,
    StaffingResponse,
)
from .staffing import RouterEngine


app = FastAPI(
    title="Personal Coding Router Service",
    version="1.0.13",
    description="Deterministic-first model/agent routing for a personal coding automation platform.",
)


def require_auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("ROUTER_API_TOKEN", "").strip()
    if not expected or expected in {"CHANGE_ME", "change-me"}:
        raise HTTPException(status_code=503, detail="ROUTER_API_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def engine() -> RouterEngine:
    return RouterEngine(get_config())


@app.get("/health")
def health() -> dict[str, Any]:
    cfg = get_config()
    return {
        "status": "ok",
        "service": "router-service",
        "version": "1.0.13",
        "registry_version": cfg["models"].get("version", 1),
        "policy_version": cfg["policy"].get("version", 1),
    }


@app.get("/v1/models", dependencies=[Depends(require_auth)])
def models() -> dict[str, Any]:
    cfg = get_config()["models"]
    public = {}
    for model_id, model in cfg.get("models", {}).items():
        public[model_id] = {
            "kind": model.get("kind"),
            "provider": model.get("provider"),
            "adapter": model.get("adapter"),
            "model": model.get("model"),
            "tier": model.get("tier"),
            "cost_class": model.get("cost_class"),
            "roles": model.get("roles", []),
        }
    return {"version": cfg.get("version", 1), "models": public}


@app.post("/v1/route", response_model=RoutingResponse, dependencies=[Depends(require_auth)])
def route(payload: RoutingRequest) -> RoutingResponse:
    try:
        return engine().route(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/staff", response_model=StaffingResponse, dependencies=[Depends(require_auth)])
def staff(payload: StaffingRequest) -> StaffingResponse:
    try:
        return engine().staff(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/reassess", response_model=ReassessResponse, dependencies=[Depends(require_auth)])
def reassess(payload: ReassessRequest) -> ReassessResponse:
    return engine().reassess(payload)


@app.post("/v1/admin/reload", dependencies=[Depends(require_auth)])
def reload_config() -> dict[str, str]:
    clear_config_cache()
    get_config()
    return {"status": "reloaded"}
