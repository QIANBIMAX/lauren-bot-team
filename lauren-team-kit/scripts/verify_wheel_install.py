"""Install the built wheel outside the source tree and import it.

Uses ``pip install --target`` so it does not need the stdlib venv module.
The import runs with a cwd that is not this repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    kit = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="lauren-wheel-") as tmp_name:
        tmp = Path(tmp_name)
        wheelhouse = tmp / "wheels"
        target = tmp / "install"
        wheelhouse.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--wheel-dir",
                str(wheelhouse),
                str(kit),
            ],
            check=True,
        )
        wheels = list(wheelhouse.glob("lauren_team_kit-*.whl"))
        if len(wheels) != 1:
            print(f"expected one lauren_team_kit wheel, found {wheels}", file=sys.stderr)
            return 1
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--target",
                str(target),
                str(wheels[0]),
            ],
            check=True,
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(target)
        env.pop("PYTHONSAFEPATH", None)
        probe = (
            "import jsonschema\n"
            "from lauren_team_kit.protocol import schema_path\n"
            "from lauren_team_kit.doctor import collect_report\n"
            "path = schema_path()\n"
            "assert path.is_file(), path\n"
            "assert path.name == 'task-protocol.schema.json'\n"
            "report = collect_report()\n"
            "assert report['workbench']['omb_delegate'] == 'not_connected'\n"
            "assert report['workbench']['probed'] is False\n"
            "print('WHEEL OK', path)\n"
            "import importlib.metadata as metadata\n"
            "print('jsonschema', metadata.version('jsonschema'))\n"
        )
        subprocess.run(
            [sys.executable, "-c", probe],
            cwd=tmp,
            env=env,
            check=True,
        )
        sdist_dir = tmp / "sdist"
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "build"],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "build", "--sdist", "--outdir", str(sdist_dir), str(kit)],
            check=True,
        )
        archives = [path for path in sdist_dir.glob("*.tar.gz") if "lauren" in path.name]
        if len(archives) != 1:
            print(f"expected one sdist, found {archives}", file=sys.stderr)
            return 1
        print("SDIST OK", archives[0].name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
