#!/usr/bin/env python3
"""Exercise a built wheel in a clean venv outside the source checkout."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import venv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel-dir', type=Path, required=True)
    args = parser.parse_args()
    wheels = list(args.wheel_dir.glob('raee_lite-*.whl'))
    if len(wheels) != 1:
        raise SystemExit('Require exactly one freshly built RAEE wheel')
    wheel = wheels[0].resolve(strict=True)
    tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())
    with tempfile.TemporaryDirectory(prefix='raee-installed-') as folder:
        root = Path(folder).resolve(strict=True)
        venv.EnvBuilder(with_pip=True).create(root / 'venv')
        python = root / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        # -I deliberately ignores PYTHONIOENCODING. Select UTF-8 explicitly for
        # redirected output on Windows Python versions before the UTF-8 default.
        python_command = (str(python), '-I', '-X', 'utf8')
        console = python.parent / ('raee-lite.exe' if os.name == 'nt' else 'raee-lite')
        project = root / 'project'
        project.mkdir()
        env = {key: value for key, value in os.environ.items() if key not in {'PYTHONPATH', 'PYTHONHOME'}}
        env['PYTHONIOENCODING'] = 'utf-8'

        def run(*argv, expected=0, cwd=project):
            command = [str(arg) for arg in argv]
            try:
                result = subprocess.run(command, cwd=cwd, env=env, timeout=120)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SystemExit(f'Installed-package smoke failed: {command!r}: {exc}') from exc
            if result.returncode != expected:
                raise SystemExit(f'Installed-package smoke failed: {command!r}, '
                                 f'exit {result.returncode} (expected {expected})')

        run(*python_command, '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel))
        run(*python_command, '-m', 'pip', 'check')
        run(*python_command, '-c', "from importlib.resources import files; import importlib.util; "
            "assert importlib.util.find_spec('cryptography') is None; "
            "assert files('raee_lite').joinpath('skill_template.md').read_text(encoding='utf-8')")
        # A working module does not prove the wheel generated a working console
        # executable. Exercise both, including propagation of a nonzero exit.
        for name, command in (
            ('module', (*python_command, '-m', 'raee_lite')),
            ('console', (str(console),)),
        ):
            cli_project = project / name
            cli_project.mkdir()
            print(f'Checking installed {name} entry point', flush=True)
            run(*command, '--version', cwd=cli_project)
            run(*command, 'init', cwd=cli_project)
            run(*command, 'add', 'Package installation works', cwd=cli_project)
            run(*command, 'expect', '--for', 'R1', '--kind', 'unit', cwd=cli_project)
            run(*command, 'status', expected=1, cwd=cli_project)
            run(*command, 'check', cwd=cli_project)
        run(*python_command, '-c', "from raee_lite.attestation import _crypto\n"
            "try:\n _crypto()\n"
            "except ValueError as exc:\n assert 'raee-lite[attest]' in str(exc)\n"
            "else:\n raise AssertionError('Missing optional dependency was silently accepted')\n")
    print('Installed wheel: module and console CLIs, packaged template '
          'and optional-dependency boundary passed.')


if __name__ == '__main__':
    main()
