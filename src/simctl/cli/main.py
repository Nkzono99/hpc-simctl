"""Main CLI application entry point."""

from __future__ import annotations

import typer

from simctl.cli.analyze import collect, plot, summarize
from simctl.cli.clone import clone
from simctl.cli.config import config_app
from simctl.cli.context import context
from simctl.cli.create import create, sweep
from simctl.cli.dashboard import dashboard
from simctl.cli.extend import extend
from simctl.cli.history import history
from simctl.cli.init import doctor, init
from simctl.cli.jobs import jobs
from simctl.cli.knowledge import knowledge_app
from simctl.cli.list import list_runs
from simctl.cli.log import log
from simctl.cli.manage import archive, cancel, delete, purge_work
from simctl.cli.new import new
from simctl.cli.notes import append as notes_append
from simctl.cli.notes import list_notes as notes_list
from simctl.cli.notes import show as notes_show
from simctl.cli.setup import setup
from simctl.cli.status import status, sync
from simctl.cli.submit import run_cmd
from simctl.cli.update import update
from simctl.cli.update_refs import update_refs

case_app = typer.Typer(
    name="case",
    help="Case template commands.",
)
case_app.command("new")(new)

runs_app = typer.Typer(
    name="runs",
    help="Run lifecycle, survey expansion, and run listing commands.",
)
runs_app.command("create")(create)
runs_app.command("sweep")(sweep)
runs_app.command("submit")(run_cmd)
runs_app.command("status")(status)
runs_app.command("sync")(sync)
runs_app.command("log")(log)
runs_app.command("list")(list_runs)
runs_app.command("jobs")(jobs)
runs_app.command("history")(history)
runs_app.command("dashboard")(dashboard)
runs_app.command("clone")(clone)
runs_app.command("extend")(extend)
runs_app.command("archive")(archive)
runs_app.command("purge-work")(purge_work)
runs_app.command("cancel")(cancel)
runs_app.command("delete")(delete)

analyze_app = typer.Typer(
    name="analyze",
    help="Analysis and reporting commands for runs and surveys.",
)
analyze_app.command("summarize")(summarize)
analyze_app.command("collect")(collect)
analyze_app.command("plot")(plot)

notes_app = typer.Typer(
    name="notes",
    help="Lab notebook commands (notes/YYYY-MM-DD.md).",
)
notes_app.command("append")(notes_append)
notes_app.command("list")(notes_list)
notes_app.command("show")(notes_show)

app = typer.Typer(
    name="simctl",
    help="HPC simulation run management CLI tool.",
    no_args_is_help=True,
)

app.command("init")(init)
app.command("setup")(setup)
app.command("doctor")(doctor)
app.add_typer(config_app, name="config")
app.add_typer(knowledge_app, name="knowledge")
app.command("context")(context)
app.add_typer(case_app, name="case")
app.add_typer(runs_app, name="runs")
app.add_typer(analyze_app, name="analyze")
app.add_typer(notes_app, name="notes")
app.command("update")(update)
app.command("update-refs")(update_refs)

if __name__ == "__main__":
    app()
