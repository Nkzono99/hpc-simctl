"""Main CLI application entry point."""

from __future__ import annotations

import typer

from simctl.cli.analyze import collect, summarize
from simctl.cli.clone import clone
from simctl.cli.config import config_app
from simctl.cli.create import create, sweep
from simctl.cli.init import doctor, init
from simctl.cli.list import list_runs
from simctl.cli.manage import archive, purge_work
from simctl.cli.status import status, sync
from simctl.cli.submit import run_cmd, submit

app = typer.Typer(
    name="simctl",
    help="HPC simulation run management CLI tool.",
    no_args_is_help=True,
)

app.command("init")(init)
app.command("doctor")(doctor)
app.add_typer(config_app, name="config")
app.command("create")(create)
app.command("sweep")(sweep)
app.command("run")(run_cmd)
app.command("submit")(submit)
app.command("status")(status)
app.command("sync")(sync)
app.command("list")(list_runs)
app.command("clone")(clone)
app.command("summarize")(summarize)
app.command("collect")(collect)
app.command("archive")(archive)
app.command("purge-work")(purge_work)

if __name__ == "__main__":
    app()
