from __future__ import annotations

from fastapi import APIRouter, Request

from ..auth import resolve_identity, user_workspace_client
from ..config import get_settings

router = APIRouter(tags=["meta"])


@router.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "app_mode": s.app_mode, "auth_mode": s.auth_mode}


@router.get("/api/health/deep")
def health_deep(request: Request) -> dict:
    """Liveness + warehouse/Genie reachability (fast-fail, used by the UI banner)."""
    s = get_settings()
    out: dict = {"status": "ok", "app_mode": s.app_mode, "warehouse": None, "genie": None}
    if s.mock:
        out.update(warehouse="mock", genie="mock")
        return out
    try:
        w = user_workspace_client(resolve_identity(request))
        wh = w.warehouses.get(s.warehouse_id)
        out["warehouse"] = str(wh.state.value if wh.state else "unknown")
    except Exception as e:  # reachability signal, not a crash
        out["warehouse"] = f"error: {type(e).__name__}"
        out["status"] = "degraded"
    try:
        import httpx

        ident = resolve_identity(request)
        headers = {"Authorization": f"Bearer {ident.token}"} if ident.token else {}
        r = httpx.get(f"{s.host}/api/2.0/genie/spaces/{s.genie_space_id}", headers=headers, timeout=10)
        out["genie"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
    except Exception as e:
        out["genie"] = f"error: {type(e).__name__}"
        out["status"] = "degraded"
    return out


@router.get("/api/me")
def me(request: Request) -> dict:
    s = get_settings()
    ident = resolve_identity(request, s)
    return {
        "user": ident.user,
        "auth_mode": ident.mode,
        "obo_token_present": bool(ident.token),
        "app_mode": s.app_mode,
        "genie_space_id": s.genie_space_id or None,
        "catalog": s.uc_catalog,
        "schema": s.uc_schema,
        "features": {"streaming": s.feature_streaming, "persistence": s.feature_persistence},
    }
