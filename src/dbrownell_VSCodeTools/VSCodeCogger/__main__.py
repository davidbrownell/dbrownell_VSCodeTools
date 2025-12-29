"""Run cog on VSCode configuration files."""

import importlib
import inspect
import io
import os
import sys
import textwrap

from pathlib import Path
from typing import Annotated

import typer

from cogapp import Cog
from dbrownell_Common import ExecuteTasks
from dbrownell_Common.ContextlibEx import ExitStack
from dbrownell_Common.InflectEx import inflect
from dbrownell_Common import TextwrapEx
from dbrownell_Common.Streams.DoneManager import DoneManager, Flags as DoneManagerFlags
from typer.core import TyperGroup


# ----------------------------------------------------------------------
class NaturalOrderGrouper(TyperGroup):  # noqa: D101
    # ----------------------------------------------------------------------
    def list_commands(self, *args, **kwargs) -> list[str]:  # noqa: ARG002, D102
        return list(self.commands.keys())


# ----------------------------------------------------------------------
app = typer.Typer(
    cls=NaturalOrderGrouper,
    help=__doc__,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    pretty_exceptions_enable=False,
)


# ----------------------------------------------------------------------
def _GenerateCogToolsDir() -> Path:
    this_dir = Path(__file__).parent

    cog_tools_dir = this_dir / "CogTools"
    assert cog_tools_dir.is_dir(), cog_tools_dir

    return cog_tools_dir


_cog_tools_dir = _GenerateCogToolsDir()


# ----------------------------------------------------------------------
def _CreateHelp() -> str:
    # Get the plugin content
    plugin_content_lines: list[list[str]] = []

    parent_display_dir = Path(__file__).parent.parent

    os.environ["__extracting_documentation__"] = "1"  # noqa: SIM112
    with ExitStack(lambda: os.environ.pop("__extracting_documentation__")):
        for plugin in _cog_tools_dir.iterdir():
            if not plugin.is_file():
                continue

            if plugin.name == "__init__.py":
                continue

            sys.path.insert(0, str(plugin.parent))
            with ExitStack(lambda: sys.path.pop(0)):
                mod = importlib.import_module(plugin.stem)
                assert mod is not None

                plugin_content_lines.append(
                    [
                        plugin.stem,
                        inspect.getdoc(mod) or "",
                        str(plugin.relative_to(parent_display_dir)),
                    ],
                )

                del sys.modules[plugin.stem]

    plugin_content = TextwrapEx.Indent(
        TextwrapEx.CreateTable(
            [
                "CogTools Name",
                "Description",
                "Source Code",
            ],
            plugin_content_lines,
        ),
        4,
    )

    # Return the help string
    return textwrap.dedent(
        """\
        Update launch.json using cog.

        Edit 'launch.json' with the code below. '<CogTools Name Here>' is the name of the
        python file within the `./CogTools` subdirectory that contains the functionality that
        you would like to use.

        launch.json:

        {{
            ...
            "configurations": [
                ...

                // \\[\\[\\[cog import <CogTools Name Here>]]]
                // \\[\\[\\[end]]]

                ...
            ]
        }}

        '<CogTools Name Here>' can be one of:

        {}

        Example:
            To populate tests based on functionality in `./CogTools/PopulateTests.py`:

            launch.json:

            {{
                ...
                "configurations": [
                    ...

                    // \\[\\[\\[cog import PopulateTests]]]
                    // \\[\\[\\[end]]]

                    ...
                ]
            }}

        """,
    ).format(plugin_content)


# ----------------------------------------------------------------------
@app.command("UpdateLaunchFile", help=_CreateHelp(), no_args_is_help=True)
def UpdateLaunchFile(  # noqa: D103
    input_file_or_directory: Annotated[
        Path,
        typer.Argument(
            exists=True, resolve_path=True, help="Input filename or directory used to search for input files."
        ),
    ] = Path.cwd(),  # noqa: B008
    single_threaded: Annotated[  # noqa: FBT002
        bool,
        typer.Option("--single-threaded", help="Execute with a single thread."),
    ] = False,
    quiet: Annotated[  # noqa: FBT002
        bool,
        typer.Option("--quiet", help="Reduce the amount of information written to the terminal."),
    ] = False,
    verbose: Annotated[  # noqa: FBT002
        bool,
        typer.Option("--verbose", help="Write verbose information to the terminal."),
    ] = False,
    debug: Annotated[  # noqa: FBT002
        bool,
        typer.Option("--debug", help="Write debug information to the terminal."),
    ] = False,
) -> None:
    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        search_filename = "launch.json"

        filenames: list[Path] = _GetFiles(dm, input_file_or_directory, search_filename)

        if not filenames:
            dm.WriteLine(f"No '{search_filename}' files were found.\n")
            return

        tasks = [ExecuteTasks.TaskData(str(filename), filename) for filename in filenames]

        # ----------------------------------------------------------------------
        def Transform(context: Path, status: ExecuteTasks.Status) -> None:  # noqa: ARG001
            _CogFile(context)

        # ----------------------------------------------------------------------

        ExecuteTasks.TransformTasks(
            dm,
            "Cogging",
            tasks,
            Transform,
            quiet=quiet,
            max_num_threads=1 if single_threaded else None,
        )

        if len(tasks) == 1 and dm.result != 0:
            content = tasks[0].log_filename.read_text()

            func = dm.WriteError if dm.result < 0 else dm.WriteWarning
            func(content + "\n\n")


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
def _GetFiles(
    dm: DoneManager,
    input_file_or_directory: Path,
    search_filename: str,
) -> list[Path]:
    if input_file_or_directory.is_file():
        assert input_file_or_directory.name == search_filename, (
            input_file_or_directory.name,
            search_filename,
        )
        return [input_file_or_directory]

    all_files: list[Path] = []

    with dm.Nested(
        f"Searching for '{search_filename}' files in '{input_file_or_directory}'...",
        lambda: "{} found".format(inflect.no("file", len(all_files))),
        suffix="\n",
    ) as search_dm:
        for root, _, filenames in os.walk(input_file_or_directory):
            for filename in filenames:
                if filename == search_filename:
                    fullpath = Path(root) / filename

                    search_dm.WriteVerbose(f"'{fullpath}' found.")
                    all_files.append(fullpath)

    return all_files


# ----------------------------------------------------------------------
def _CogFile(filename: Path) -> None:
    # Invoke cog
    sink = io.StringIO()

    cog = Cog()

    cog.set_output(stdout=sink, stderr=sink)

    result = cog.main(
        [
            "custom_cog",  # Fake script name
            "-c",  # checksum
            "-e",  # Warn if a file has no cog code in it
            "-r",  # Replace
            "--verbosity=0",
            "-I",
            str(_cog_tools_dir),
            str(filename),
        ],
    )

    output = sink.getvalue()

    if result == 0:
        lines = output.rstrip().split("\n")

        if lines[-1].startswith("Warning:"):
            result = 1

    if result != 0:
        msg = textwrap.dedent(
            """\
            Cogging '{}' failed with the result code '{}'.

            Output:
            {}
            """,
        ).format(
            filename,
            result,
            TextwrapEx.Indent(output, 4),
        )

        raise Exception(msg)


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app()
