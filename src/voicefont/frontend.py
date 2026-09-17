"""Serve the built React bundle locally, without a Node runtime or CDN."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


def bundle_root() -> Path:
    packaged = Path(__file__).parent / "web"
    return packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / "frontend/dist"


def mount_frontend(app: FastAPI, root: Path | None = None) -> None:
    root = root if root is not None else bundle_root()

    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse("/calibrate")

    @app.get("/calibrate", include_in_schema=False)
    def calibrate():
        if not (root / "index.html").is_file():
            return JSONResponse(
                {"detail": "React frontend not built. Run npm run build in frontend/."},
                status_code=503,
            )
        return FileResponse(root / "index.html", media_type="text/html")

    app.mount(
        "/assets", StaticFiles(directory=root / "assets", check_dir=False), name="react-assets"
    )
