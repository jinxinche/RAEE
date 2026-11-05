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
    with tempfile.TemporaryDirectory(prefix='raee-installed-') as folder:
        root = Path(folder).resolve(strict=True)
        venv.EnvBuilder(with_pip=True).create(root / 'venv')
        python = root / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        project = root / 'project'
        project.mkdir()
        env = {key: value for key, value in os.environ.items() if key not in {'PYTHONPATH', 'PYTHONHOME'}}
        env['PYTHONIOENCODING'] = 'utf-8'

        def run(*argv, expected=0):
            result = subprocess.run([str(python), '-I', *argv], cwd=project, env=env, timeout=120)
            if result.returncode != expected:
                raise SystemExit(f'Installed-package smoke failed: {argv[0]}, exit {result.returncode}')

        run('-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel))
        run('-m', 'pip', 'check')
        run('-c', "from importlib.resources import files; import importlib.util; "
            "assert importlib.util.find_spec('cryptography') is None; "
            "assert files('raee_lite').joinpath('skill_template.md').read_text(encoding='utf-8')")
        run('-m', 'raee_lite', '--version')
        run('-m', 'raee_lite', 'init')
        run('-m', 'raee_lite', 'add', 'Package installation works')
        run('-m', 'raee_lite', 'expect', '--for', 'R1', '--kind', 'unit')
        run('-m', 'raee_lite', 'status', expected=1)
        run('-m', 'raee_lite', 'check')
        run('-c', "from raee_lite.attestation import _crypto\n"
            "try:\n _crypto()\n"
            "except ValueError as exc:\n assert 'raee-lite[attest]' in str(exc)\n"
            "else:\n raise AssertionError('Missing optional dependency was silently accepted')\n")
    print('Installed wheel: core CLI, packaged template and optional-dependency boundary passed.')


if __name__ == '__main__':
    main()
