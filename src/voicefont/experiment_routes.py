"""Same-origin, bounded local acoustic experiment endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, StrictBool
from starlette.concurrency import run_in_threadpool

from .calibration import CalibrationError
from .calibration_routes import StrictBody, _json, _same_origin
from .experiment import ExperimentBusy, ExperimentError, ExperimentService, capabilities


class ExperimentBody(StrictBody):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    consent: StrictBool


async def _call(function, *args, **kwargs):
    try:
        return await run_in_threadpool(function, *args, **kwargs)
    except ExperimentBusy as exc:
        raise HTTPException(409, str(exc)) from None
    except (ExperimentError, CalibrationError) as exc:
        raise HTTPException(422, str(exc)) from None
    except FileNotFoundError:
        raise HTTPException(404, "session or experiment not found") from None
    except OSError:
        raise HTTPException(503, "local experiment storage is unavailable") from None


def create_experiment_router(profile_root: str | Path):
    service = ExperimentService(profile_root)
    router = APIRouter(prefix="/experiments", dependencies=[Depends(_same_origin)])

    @router.get("/capabilities")
    def get_capabilities():
        return capabilities()

    @router.post("", status_code=202)
    async def start_experiment(request: Request):
        body = await _json(request, ExperimentBody)
        return await _call(service.start, body.session_id, consent=body.consent)

    @router.get("/{experiment_id}")
    async def get_experiment(experiment_id: str):
        return await _call(service.get, experiment_id)

    return router
