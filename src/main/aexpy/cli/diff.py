import click
from click import ClickException

from ..env import env
from . import interactive


@click.command()
@click.argument("project")
@click.argument("old", default="")
@click.argument("new", default="")
@click.option("-a", "--all", is_flag=True, default=False, help="All version.")
def diff(project: str, old: str = "", new: str = "", all: bool = False) -> None:
    """Compare API."""
    if all:
        from ..jobs import diffs

        diffs.diffProject(project)
    else:
        if not old or not new:
            raise ClickException("Please specify old and new version.")
        from ..analyses.environment import analyze
        from ..diffs import serializer
        from ..diffs.environment import diff
        from ..downloads import releases, wheels
        from ..jobs import diffs

        rels = releases.getReleases(project)
        oldDownloadInfo = releases.getDownloadInfo(rels[old])
        newDownloadInfo = releases.getDownloadInfo(rels[new])
        if oldDownloadInfo is None or newDownloadInfo is None:
            raise ClickException("No this release")

        oldDownloaded = wheels.downloadWheel(oldDownloadInfo)
        newDownloaded = wheels.downloadWheel(newDownloadInfo)
        oldApi = analyze(oldDownloaded)
        newApi = analyze(newDownloaded)
        result = diff(oldApi, newApi)
        if env.interactive:
            interactive.interact({
                "diff": result,
                "O": oldApi,
                "N": newApi,
                "D": result,
                "OM": result.old,
                "NM": result.new,
                "entries": result.entries,
                "E": result.entries,
                "EL": list(result.entries.values()),
                "kind": result.kind,
            })
        else:
            click.echo(serializer.serialize(result, indent=4))