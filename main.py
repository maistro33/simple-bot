"""
FACT DROP AI STUDIO — Command Line Interface.

Entry point for running the full affiliate content generation pipeline
from the terminal. Built with Typer + Rich for a polished, discoverable
CLI experience while remaining fully scriptable for automation.

Usage:
    python main.py create "https://www.amazon.com/dp/B0EXAMPLE"
    python main.py list
    python main.py show <project_id>
    python main.py resume <project_id>
    python main.py export <project_id>
    python main.py undo <project_id>
    python main.py delete <project_id>
    python main.py backups <project_id>
    python main.py resumable
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.constants import ExportFormat  # noqa: E402
from core.application import get_application  # noqa: E402
from core.exceptions import FactDropError  # noqa: E402
from core.logger import get_logger  # noqa: E402

app = typer.Typer(
    name="fact-drop-ai",
    help="FACT DROP AI STUDIO — AI-powered affiliate content creation pipeline.",
    add_completion=True,
)
console = Console()
logger = get_logger(__name__)


@app.command()
def create(
    input_text: str = typer.Argument(..., help="Product URL, title, or free-form description."),
    name: str = typer.Option(None, "--name", "-n", help="Optional custom project name."),
) -> None:
    """Create a new project and run it through the entire content pipeline."""
    application = get_application()
    console.print(Panel.fit(f"[bold cyan]Starting new project[/bold cyan]\n{input_text}", title="Fact Drop AI Studio"))

    try:
        with console.status("[bold green]Running full pipeline...[/bold green]", spinner="dots"):
            context = application.create_and_run_project(input_text, name=name)
    except FactDropError as exc:
        console.print(f"[bold red]Pipeline failed:[/bold red] {exc}")
        raise typer.Exit(code=1)

    console.print("[bold green]✔ Pipeline completed successfully![/bold green]")
    if context.get("export_path"):
        console.print(f"Export bundle: [bold]{context['export_path']}[/bold]")
    if context.get("report", {}).get("quality_score") is not None:
        console.print(f"Quality score: [bold]{context['report']['quality_score']}[/bold] / 100")


@app.command(name="list")
def list_projects(limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of projects to show.")) -> None:
    """List recent projects."""
    application = get_application()
    projects = application.project_manager.list_projects(limit=limit)

    table = Table(title="Fact Drop AI Studio — Projects")
    table.add_column("ID", style="dim", overflow="fold")
    table.add_column("Name")
    table.add_column("Stage")
    table.add_column("Status")
    table.add_column("Updated")

    for project in projects:
        table.add_row(
            project.id, project.name, project.current_stage.value, project.status.value,
            project.updated_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


@app.command()
def show(project_id: str = typer.Argument(..., help="Project ID to display.")) -> None:
    """Show full details for a single project."""
    application = get_application()
    try:
        project = application.project_manager.get_project(project_id)
    except FactDropError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(code=1)

    console.print(Panel.fit(
        f"[bold]{project.name}[/bold]\n\n"
        f"Stage: {project.current_stage.value}\n"
        f"Status: {project.status.value}\n"
        f"Category: {project.category.value}\n"
        f"Brand: {project.brand_name or 'N/A'}\n"
        f"Product title: {project.product_title or 'N/A'}\n"
        f"Created: {project.created_at}\n"
        f"Updated: {project.updated_at}",
        title=f"Project {project.id}",
    ))


@app.command()
def resume(project_id: str = typer.Argument(..., help="Project ID to resume.")) -> None:
    """Resume a previously paused or failed project from its last completed stage."""
    application = get_application()
    try:
        with console.status("[bold green]Resuming pipeline...[/bold green]", spinner="dots"):
            application.resume_project(project_id)
    except FactDropError as exc:
        console.print(f"[bold red]Resume failed:[/bold red] {exc}")
        raise typer.Exit(code=1)
    console.print("[bold green]✔ Project resumed and completed successfully![/bold green]")


@app.command()
def resumable() -> None:
    """List every project that was interrupted mid-pipeline and can be resumed."""
    application = get_application()
    projects = application.list_resumable_projects()
    if not projects:
        console.print("[dim]No resumable projects found.[/dim]")
        return

    table = Table(title="Resumable Projects")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Stage")
    table.add_column("Status")
    for project in projects:
        table.add_row(project.id, project.name, project.current_stage.value, project.status.value)
    console.print(table)


@app.command()
def export(
    project_id: str = typer.Argument(..., help="Project ID to export."),
    export_format: str = typer.Option("zip", "--format", "-f", help="Export format: zip or folder."),
) -> None:
    """Export a completed project's full asset bundle."""
    application = get_application()
    fmt = ExportFormat.ZIP if export_format == "zip" else ExportFormat.FOLDER
    try:
        path = application.export_project(project_id, export_format=fmt)
    except FactDropError as exc:
        console.print(f"[bold red]Export failed:[/bold red] {exc}")
        raise typer.Exit(code=1)
    console.print(f"[bold green]✔ Exported to:[/bold green] {path}")


@app.command()
def undo(project_id: str = typer.Argument(..., help="Project ID to revert.")) -> None:
    """Undo the last recorded change for a project."""
    application = get_application()
    snapshot = application.undo_last_action(project_id)
    if snapshot is None:
        console.print("[yellow]Nothing to undo for this project.[/yellow]")
    else:
        console.print(f"[bold green]✔ Reverted to stage:[/bold green] {snapshot.get('current_stage')}")


@app.command()
def delete(
    project_id: str = typer.Argument(..., help="Project ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Permanently delete a project and its on-disk assets."""
    if not yes:
        confirmed = typer.confirm(f"Permanently delete project {project_id}?")
        if not confirmed:
            raise typer.Abort()

    application = get_application()
    deleted = application.project_manager.delete_project(project_id)
    if deleted:
        console.print("[bold green]✔ Project deleted.[/bold green]")
    else:
        console.print("[yellow]Project not found.[/yellow]")


@app.command()
def backups(project_id: str = typer.Argument(..., help="Project ID to list backups for.")) -> None:
    """List all disaster-recovery backups available for a project."""
    from core.backup_manager import BackupManager

    manager = BackupManager()
    files = manager.list_backups(project_id)
    if not files:
        console.print("[dim]No backups found for this project.[/dim]")
        return
    for path in files:
        console.print(f"- {path}")


def run() -> None:
    """Console-script entry point (also invoked when running ``python main.py``)."""
    app()


if __name__ == "__main__":
    run()
