"""Opt-in Docker-based replay of checks against a bounded, sanitized source snapshot.

Security boundary: a restricted container, NOT a VM or proof against kernel/
Docker daemon compromise. Never forward host environment, credentials or sockets.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from . import core
from .contracts import KINDS
from .safe_process import run as bounded_run

MAX_FILES = 5000
MAX_FILE_SIZE = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
DEFAULT_MEMORY_MB = 512
DEFAULT_CPUS = 1.0
DEFAULT_PIDS = 64
MAX_TIMEOUT = 3600
DENY_DIRS = {'.git', '.raee', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
             '.tox', '.mypy_cache', '.next', 'dist', 'build', '.idea', '.vscode', '.aws', '.ssh',
             '.config', '.kube', 'coverage', '.nyc_output'}
DENY_FILENAMES = {'id_rsa', 'id_ed25519', 'credentials', 'credentials.json',
                  'service-account.json', '.npmrc', '.pypirc', '.netrc', '.dockerconfigjson',
                  '.git-credentials', 'secrets.json', 'secret.json', 'token.json', 'auth.json'}
DENY_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.keystore', '.kdbx'}
IMAGE_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_./:@+-]{0,240}$')
IMAGE_ID_RE = re.compile(r'^sha256:[a-f0-9]{64}$')
START_SCRIPT = 'cp -R /raee-input/. /workspace/ && cd /workspace && exec "$@"'


def _denied_filename(name: str) -> bool:
    low = name.lower()
    return (low in DENY_FILENAMES or low.startswith('.env') or low.endswith(tuple(DENY_SUFFIXES))
            or low.endswith('.secret') or low.endswith('.secrets'))


def stage_snapshot(root: Path, staging: Path) -> dict:
    """Copy only regular non-symlink files; fail closed on size/count or read races.

    This is deliberately NOT a complete Git checkout. Exclusions are reported.
    Root must be caller-owned/trusted: simultaneous malicious filesystem mutation
    is outside the guaranteed boundary, even with O_NOFOLLOW checks.
    """
    root = root.resolve(strict=True)
    if not root.is_dir() or root == Path(root.anchor):
        raise ValueError('Refusing root filesystem as project')
    staging.mkdir(mode=0o755, parents=False, exist_ok=False)
    digest = hashlib.sha256()
    files = 0
    total = 0
    exclusions = []
    included = []
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        folder = Path(directory)
        rel_dir = folder.relative_to(root)
        # os.walk order otherwise varies across hosts.
        good_dirs = []
        for name in sorted(dirnames):
            rel = (rel_dir / name).as_posix()
            candidate = folder / name
            if candidate.is_symlink():
                exclusions.append({'path': rel, 'reason': 'directory_symlink_excluded'})
            elif name in DENY_DIRS:
                exclusions.append({'path': rel, 'reason': 'excluded_directory_or_symlink'})
            else:
                good_dirs.append(name)
        dirnames[:] = good_dirs
        outdir = staging / rel_dir
        outdir.mkdir(parents=True, exist_ok=True, mode=0o755)
        for name in sorted(filenames):
            source = folder / name
            rel = (rel_dir / name).as_posix()
            if _denied_filename(name):
                exclusions.append({'path': rel, 'reason': 'sensitive_name_excluded'})
                continue
            try:
                st = source.lstat()
                if not stat.S_ISREG(st.st_mode):
                    exclusions.append({'path': rel, 'reason': 'not_regular_file_or_symlink'})
                    continue
                if st.st_size > MAX_FILE_SIZE:
                    raise ValueError(f'Snapshot exceeds per-file limit at {rel}')
                if files + 1 > MAX_FILES or total + st.st_size > MAX_TOTAL_BYTES:
                    raise ValueError('Snapshot exceeds 5000-file / 64-MiB budget; no execution performed')
                flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                fd = os.open(source, flags)
                try:
                    fst = os.fstat(fd)
                    if not stat.S_ISREG(fst.st_mode) or fst.st_dev != st.st_dev or fst.st_ino != st.st_ino:
                        raise ValueError(f'Changed or unsafe file during snapshot: {rel}')
                    dest = outdir / name
                    filehash = hashlib.sha256()
                    size = 0
                    with os.fdopen(fd, 'rb', closefd=False) as inp, dest.open('xb') as out:
                        while True:
                            chunk = inp.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > MAX_FILE_SIZE or total + size > MAX_TOTAL_BYTES:
                                raise ValueError(f'Snapshot exceeded byte budget at {rel}')
                            filehash.update(chunk)
                            out.write(chunk)
                    fst_after = os.fstat(fd)
                    if (size != st.st_size or fst_after.st_mtime_ns != fst.st_mtime_ns
                            or fst_after.st_size != fst.st_size):
                        raise ValueError(f'File changed while copying: {rel}')
                    dest.chmod(0o755 if st.st_mode & 0o111 else 0o644)
                    digest.update(rel.encode('utf-8', 'surrogateescape') + b'\x00' + filehash.digest())
                    files += 1
                    total += size
                    if len(included) < 200:
                        included.append(rel)
                finally:
                    os.close(fd)
            except (OSError, UnicodeError) as exc:
                raise ValueError(f'Snapshot refused unreadable or unsafe file {rel}: {type(exc).__name__}') from exc
    unsafe_count = sum(e['reason'] != 'excluded_directory_or_symlink' for e in exclusions)
    return {'sha256': digest.hexdigest(), 'files': files, 'bytes': total,
            'excluded_paths': exclusions[:100], 'excluded_total': len(exclusions), 'unsafe_excluded_total': unsafe_count,
            'included_paths_sample': included,
            'policy': 'Regular files only; hidden credentials and known generated folders excluded; no symlinks.'}


def _docker_image_id(docker: str, image: str) -> str:
    if not IMAGE_RE.fullmatch(image) or image.startswith('-'):
        raise ValueError('Invalid Docker image reference')
    try:
        process = subprocess.run([docker, 'image', 'inspect', '--format', '{{.Id}}', image],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12,
                                 text=True, check=False, env=_safe_docker_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'Docker image preflight failed: {type(exc).__name__}') from exc
    image_id = process.stdout.strip()
    if process.returncode != 0 or not IMAGE_ID_RE.fullmatch(image_id):
        raise ValueError('Docker image not available locally; obtain a trusted image explicitly, then retry')
    return image_id


def _safe_docker_env() -> dict:
    # Keep Docker context variables for user-configured daemon; never export secrets into the container.
    names = ('PATH', 'HOME', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG',
             'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH', 'XDG_RUNTIME_DIR', 'SYSTEMROOT', 'WINDIR')
    return {k: os.environ[k] for k in names if k in os.environ}


def _require_local_daemon(docker: str) -> None:
    # A remote daemon may resolve source mounts on a different host. Fail closed.
    host_override = os.environ.get('DOCKER_HOST', '')
    if host_override and not host_override.startswith(('unix://', 'npipe://', 'fd://')):
        raise ValueError('Remote Docker daemons are unsupported for local snapshots')
    try:
        proc = subprocess.run([docker, 'context', 'inspect', '--format', '{{json .Endpoints.docker.Host}}'],
                              capture_output=True, text=True, timeout=12, check=False, env=_safe_docker_env())
        endpoint = json.loads(proc.stdout.strip()) if proc.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ValueError('Cannot establish local Docker daemon context') from exc
    if not isinstance(endpoint, str) or not endpoint.startswith(('unix://', 'npipe://', 'fd://')):
        raise ValueError('Docker context must use a local Unix socket or named pipe; remote daemons are blocked')


def build_docker_command(docker: str, image_id: str, source: Path, name: str,
                         command: list[str], memory_mb: int = DEFAULT_MEMORY_MB,
                         cpus: float = DEFAULT_CPUS, pids: int = DEFAULT_PIDS) -> list[str]:
    if not IMAGE_ID_RE.fullmatch(image_id):
        raise ValueError('Image must resolve to a local SHA-256 image ID')
    if not command or command[0].startswith('-') or any(not arg or '\x00' in arg for arg in command):
        raise ValueError('Explicit command required; no empty / NUL arguments')
    if not (128 <= memory_mb <= 4096 and .25 <= cpus <= 4 and 16 <= pids <= 256):
        raise ValueError('Resource limits outside bounded range')
    return [docker, 'run', '--rm', '--name', name, '--pull=never',
            '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges:true', '--pids-limit', str(pids),
            '--memory', f'{memory_mb}m', '--memory-swap', f'{memory_mb}m', '--cpus', str(cpus),
            '--user', '65532:65532', '--ipc=private', '--pid=private',
            '--tmpfs', '/workspace:rw,exec,nosuid,nodev,size=128m,mode=1777',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777',
            '--mount', f'type=bind,src={source},dst=/raee-input,readonly',
            '--workdir', '/workspace', '--entrypoint', '/bin/sh', '--env', 'HOME=/tmp', '--env', 'CI=true',
            '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'TMPDIR=/tmp',
            image_id, '-c', START_SCRIPT, 'raee-isolate', *command]


def replay(root: Path, requirement: str, kind: str, command: list[str], *, image: str,
           timeout: int = 120, memory_mb: int = DEFAULT_MEMORY_MB,
           dry_run: bool = False) -> dict:
    """Return isolated execution evidence, persisted only for a completed run.

    Dry-run is an inspection plan only: it never starts Docker or writes an evidence receipt.
    """
    if kind not in KINDS:
        raise ValueError(f'Unknown evidence kind: {kind}')
    if timeout < 1 or timeout > MAX_TIMEOUT:
        raise ValueError('Timeout must be 1-3600 seconds')
    if not command or any(not item or '\x00' in item for item in command):
        raise ValueError('Missing or invalid execution arguments')
    if requirement not in {r['id'] for r in core.get_manifest(root).get('requirements', [])}:
        raise ValueError(f'Unknown requirement: {requirement}')
    # Reject unsupported workspace path syntaxes rather than potentially mounting wrong directory.
    root = root.resolve(strict=True)
    if any(',' in str(p) or '\n' in str(p) or '\r' in str(p) for p in [root]):
        raise ValueError('Project path contains unsupported Docker mount delimiters')
    if not IMAGE_RE.fullmatch(image) or image.startswith('-'):
        raise ValueError('Invalid image name')
    with tempfile.TemporaryDirectory(prefix='raee-staging-') as tmp:
        staging = Path(tmp) / 'snapshot'
        if ',' in str(staging) or '\n' in str(staging) or '\r' in str(staging):
            raise ValueError('Temporary staging path unsupported for Docker mounts')
        before = core.fingerprint(root)
        snapshot = stage_snapshot(root, staging)
        after_stage = core.fingerprint(root)
        if before['sha256'] != after_stage['sha256']:
            raise ValueError('Source changed during snapshot collection; no evidence recorded')
        if dry_run:
            return {'mode': 'DRY_RUN_NOT_EXECUTED', 'snapshot': snapshot,
                    'command_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                    'requested_image': image, 'constraints': ['network=none', 'read-only root', 'cap-drop=ALL',
                    'nonroot', 'bounded memory/cpu/pids', 'read-only source snapshot'],
                    'warning': 'Preview only; no image availability check, no check executed, no receipt created.'}
        docker = shutil.which('docker')
        if not docker:
            raise ValueError('Docker executable not found. No local unsafe fallback is provided.')
        docker_path = Path(docker).resolve(strict=True)
        if docker_path == root or root in docker_path.parents:
            raise ValueError('Refusing Docker executable supplied by the project tree')
        docker = str(docker_path)
        _require_local_daemon(docker)
        image_id = _docker_image_id(docker, image)
        name = 'raee-' + secrets.token_hex(9)
        args = build_docker_command(docker, image_id, staging, name, command, memory_mb=memory_mb)
        # The snapshot is mounted read-only and containers have no host environment, home or sockets.
        code = 125
        error = None
        started = time.monotonic()
        try:
            code, error, _ = bounded_run(args, root, timeout, env=_safe_docker_env())
        finally:
            # Killing docker CLI on timeout may leave the container behind; cleanup by exact random name.
            try:
                subprocess.run([docker, 'rm', '-f', name], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10, check=False, env=_safe_docker_env())
            except (OSError, subprocess.TimeoutExpired):
                pass
        duration = round(time.monotonic() - started, 2)
        after = core.fingerprint(root)
        # Never treat Docker infrastructure errors as passing verification evidence.
        status = 'pass' if code == 0 else ('infrastructure_error' if code in (124, 125, 126, 127) else 'fail')
        ledger = core.read_json(root / core.LEDGER, {'schema': 1, 'runs': []})
        entry = {'id': f"E{len(ledger.get('runs', [])) + 1}",
                 'role': 'verification', 'origin': 'isolated_replay', 'requirement': requirement,
                 'declared_kind': kind, 'command': ['[isolated command redacted]'],
                 'command_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                 'observed_exit_code': code, 'observed_status': status,
                 'timestamp': core.utcnow(), 'duration_seconds': duration,
                 'source_fingerprint': before['sha256'],
                 'source_fingerprint_after': after['sha256'],
                 'files_inspected': before['files'],
                 'files_skipped': before['skipped'] + ([{'file': '[snapshot]', 'reason': 'sensitive_or_unsafe_paths_omitted',
                         'count': snapshot['unsafe_excluded_total']}]
                         if snapshot['unsafe_excluded_total'] else []),
                 'error': error if error else ('Docker or executed command returned reserved exit status' if status == 'infrastructure_error' else None),
                 'output_policy': 'DISCARDED_NOT_STORED',
                 'isolation': {'backend': 'docker', 'policy': 'restricted_container_not_vm',
                               'network': 'none', 'read_only_root': True,
                               'source_mount': 'read_only', 'user': '65532:65532',
                               'memory_mb': memory_mb, 'cpus': DEFAULT_CPUS, 'pids': DEFAULT_PIDS,
                               'requested_image': image, 'resolved_image_id': image_id,
                               'snapshot_sha256': snapshot['sha256'], 'snapshot_files': snapshot['files'],
                               'snapshot_bytes': snapshot['bytes'], 'snapshot_excluded_total': snapshot['excluded_total'],
                               'snapshot_excluded_paths': snapshot['excluded_paths'],
                               'limits': ['container escape not ruled out', 'source snapshot may omit inputs',
                                          'test coverage is self-declared']},
                 'change': core.git_context(root)}
        ledger.setdefault('runs', []).append(entry)
        core.write_json(root / core.LEDGER, ledger)
        return entry
