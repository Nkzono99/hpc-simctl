"""Main CLI application entry point."""

from __future__ import annotations

import typer

from simctl.cli.analyze import collect, summarize
from simctl.cli.clone import clone
from simctl.cli.config import config_app
from simctl.cli.context import context
from simctl.cli.create import create, sweep
from simctl.cli.extend import extend
from simctl.cli.history import history
from simctl.cli.init import doctor, init
from simctl.cli.jobs import jobs
from simctl.cli.knowledge import knowledge_app
from simctl.cli.list import list_runs
from simctl.cli.log import log
from simctl.cli.manage import archive, purge_work
from simctl.cli.new import new
from simctl.cli.status import status, sync
from simctl.cli.submit import run_cmd
from simctl.cli.update import update
from simctl.cli.update_refs import update_refs

app = typer.Typer(
    name="simctl",
    help="HPC simulation run management CLI tool.",
    no_args_is_help=True,
)

app.command("init")(init)
app.command("doctor")(doctor)
app.add_typer(config_app, name="config")
app.add_typer(knowledge_app, name="knowledge")
app.command("context")(context)
app.command("new")(new)
app.command("create")(create)
app.command("sweep")(sweep)
app.command("run")(run_cmd)
app.command("log")(log)
app.command("status")(status)
app.command("sync")(sync)
app.command("jobs")(jobs)
app.command("history")(history)
app.command("list")(list_runs)
app.command("clone")(clone)
app.command("extend")(extend)
app.command("summarize")(summarize)
app.command("collect")(collect)
app.command("archive")(archive)
app.command("purge-work")(purge_work)
app.command("update")(update)
app.command("update-refs")(update_refs)

if __name__ == "__main__":
    app()
