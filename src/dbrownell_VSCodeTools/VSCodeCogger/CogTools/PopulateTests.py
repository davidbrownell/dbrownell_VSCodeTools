"""Searches for and creates debug profiles for all tests found."""

import os
import textwrap

from abc import ABC, abstractmethod
from pathlib import Path

from dbrownell_Common.Types import override


# ----------------------------------------------------------------------
def Execute() -> None:  # noqa: D103
    # Do not import at the module level, as the cog package is only available when this script is invoked within a cogging context.
    import cog  # noqa: PLC0415 # ty: ignore[unresolved-import]

    parsers = [
        _PytestTestTypeParser(),
        _PythonUnittestTestTypeParser(),
    ]

    source_dir = Path(cog.inFile).parent.parent

    # Get all of the tests
    test_filenames: dict[Path, _TestTypeParser] = {}

    for root_str, directories, filenames in os.walk(source_dir):
        root = Path(root_str)

        if root.name == ".venv":
            directories[:] = []
            continue

        for filename in filenames:
            fullpath = root / filename

            parser = next((parser for parser in parsers if parser.IsSupportedFile(fullpath)), None)
            if parser is not None:
                test_filenames[fullpath] = parser

    if not test_filenames:
        return

    # Organize the tests into groups based on the directory structure
    len_source_dir_parts = len(source_dir.parts)

    groups: dict[str, list[tuple[Path, _TestTypeParser]]] = {}
    test_names_lookup: dict[str, int] = {}

    for test_filename, parser in test_filenames.items():
        test_name = test_filename.name

        if test_name in test_names_lookup:
            test_names_lookup[test_name] += 1
        else:
            test_names_lookup[test_name] = 1

        group_name = Path(*test_filename.parts[len_source_dir_parts:]).parent.as_posix()
        groups.setdefault(group_name, []).append((test_filename, parser))

    cog.outl(
        textwrap.dedent(
            """\
            //
            // This content can be updated by running 'vscodecogger' from the command line.
            //
            """,
        ).rstrip(),
    )

    for group_name, test_infos in groups.items():
        cog.outl(
            textwrap.dedent(
                """\
                // ----------------------------------------------------------------------
                // |
                // |  {}
                // |
                // ----------------------------------------------------------------------
                """,
            )
            .format(group_name)
            .rstrip(),
        )

        for test_filename, test_parser in test_infos:
            cog.outl(
                test_parser.GenerateContent(
                    group_name=group_name,
                    filename=test_filename.as_posix(),
                    dirname=test_filename.parent.as_posix(),
                    name=test_filename.name,
                    display_name="{}{}".format(
                        test_filename.stem,
                        "" if test_names_lookup[test_filename.name] == 1 else " --- {}".format(group_name),
                    ),
                ),
            )

    cog.outl("")


# ----------------------------------------------------------------------
# |
# |  Private Types
# |
# ----------------------------------------------------------------------
class _TestTypeParser(ABC):
    """Base class for parsers that can process files to be included in cog output."""

    # ----------------------------------------------------------------------
    @abstractmethod
    def IsSupportedFile(self, filename: Path) -> bool:
        """Return True if the file is supported by this parser."""
        raise Exception("Abstract method")  # noqa: EM101, TRY003

    # ----------------------------------------------------------------------
    @abstractmethod
    def GenerateContent(self, **template_args) -> str:
        """Generate content for the file."""
        raise Exception("Abstract method")  # noqa: EM101, TRY003


# ----------------------------------------------------------------------
class _PytestTestTypeParser(_TestTypeParser):
    """Process python pytest files."""

    # ----------------------------------------------------------------------
    @override
    def IsSupportedFile(self, filename: Path) -> bool:
        if filename.suffix != ".py":
            return False

        if filename.stem == "__init__":
            return False

        with filename.open(encoding="utf-8") as f:
            for line in f.readlines():
                stripped_line = line.lstrip()

                if stripped_line.startswith("import unittest"):
                    break

                if stripped_line.startswith("import pytest"):
                    return True

                if stripped_line.startswith("def test"):
                    return True

                if stripped_line.startswith("class Test"):
                    return True

        return False

    # ----------------------------------------------------------------------
    @override
    def GenerateContent(self, **template_args) -> str:
        return textwrap.dedent(
            """\
            {{
                // {filename}
                "name": "{display_name}",

                "presentation": {{
                    "hidden": false,
                    "group": "{group_name}",
                }},

                "type": "debugpy",
                "request": "launch",
                "justMyCode": false,
                "console": "integratedTerminal",

                "module": "pytest",

                "args": [
                    "{filename}",
                    "-vv",

                    "--capture=no",  // Do not capture stderr/stdout

                    // To run a test method within a class, use the following expression
                    // with the `-k` argument that follows:
                    //
                    //      <class_name> and <test_name> [and not <other_test_name>]
                    //

                    // "-k", "test_name or expression",

                    // Insert custom program args here
                ],
            }},
            """,
        ).format(**template_args)


# ----------------------------------------------------------------------
class _PythonUnittestTestTypeParser(_TestTypeParser):
    """Processes python unittest files."""

    # ----------------------------------------------------------------------
    @override
    def IsSupportedFile(self, filename: Path) -> bool:
        if filename.suffix != ".py":
            return False

        if filename.stem == "__init__":
            return False

        with filename.open(encoding="utf-8") as f:
            for line in f.readlines():
                stripped_line = line.lstrip()

                if stripped_line.startswith("import pytest"):
                    break

                if stripped_line.startswith("import unittest"):
                    return True

        return False

    # ----------------------------------------------------------------------
    @override
    def GenerateContent(self, **template_args) -> str:
        return textwrap.dedent(
            """\
            {{
                // {filename}
                "name": "{display_name}",

                "presentation": {{
                    "hidden": false,
                    "group": "{group_name}",
                }},

                "type": "python",
                "request": "launch",
                "justMyCode": false,
                "console": "integratedTerminal",

                "program": "{filename}",

                "args": [
                    // Insert custom program args here
                ],
            }},
            """,
        ).format(**template_args)


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if not os.environ.get("__extracting_documentation__", ""):  # noqa: SIM112
    Execute()
