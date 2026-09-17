"""Local-only JSON CLI for explicit-consent enrollment and acoustic similarity."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from .api import create_app, default_root
from .registry import ProfileStore

app = typer.Typer(no_args_is_help=True)
RootOption = Annotated[
    Path | None, typer.Option(help="Registry root; defaults under ~/.voicefont.")
]


@contextmanager
def errors():
    try:
        yield
    except (ValueError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None


def store(root: Path | None) -> ProfileStore:
    return ProfileStore(root if root is not None else default_root())


def emit(value):
    typer.echo(json.dumps(value, indent=2, allow_nan=False))


@app.command()
def enroll(
    reference: Annotated[Path, typer.Option()],
    voice_id: Annotated[str, typer.Option()],
    name: Annotated[str, typer.Option()],
    consent: Annotated[
        bool, typer.Option(help="I own this voice or have explicit permission.")
    ] = False,
    root: RootOption = None,
):
    with errors():
        emit(store(root).enroll(reference, voice_id=voice_id, name=name, consent=consent).to_dict())


@app.command()
def search(
    reference: Annotated[Path, typer.Option()],
    top_k: Annotated[int, typer.Option(min=1, max=100)] = 5,
    root: RootOption = None,
):
    with errors():
        emit([asdict(match) for match in store(root).search(reference, top_k=top_k)])


@app.command()
def inspect(voice_id: Annotated[str, typer.Option()], root: RootOption = None):
    with errors():
        emit(store(root).get(voice_id).to_dict())


@app.command("list")
def list_profiles(root: RootOption = None):
    with errors():
        emit([profile.to_dict() for profile in store(root).list_profiles()])


@app.command()
def serve(
    root: RootOption = None,
    host: str = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
):
    import uvicorn

    if host not in ("127.0.0.1", "localhost"):
        raise typer.BadParameter("supported hosts are 127.0.0.1 and localhost (IPv4)")
    # Keep localhost consistent with the IPv4 Host validation boundary.
    # Access logs include profile names/IDs in URLs, so never enable them by default.
    uvicorn.run(create_app(root), host="127.0.0.1", port=port, access_log=False)
