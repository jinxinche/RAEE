"""Streaming, untrusted Codex/Claude transcript importer.

Only coarse command family and exit-code metadata leave the parser. Never treats
agent-owned assertions or transcript output as independently verified tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import OrderedDict
from pathlib import Path

from . import core
from .topic_tags import tags

IMPORTS = Path('.raee/imports.json')
MAX_LINE = 512_000
MAX_BYTES = 256_000_000
MAX_EVENTS = 200_000
MAX_PENDING = 2048
MAX_OBSERVATIONS = 25_000
EXIT = re.compile(r'(?im)^\s*(?:Process exited with code|Exit code|Process exit code)\s*:?\s*(-?\d{1,6})\s*$')
CHECKS = (
    (re.compile(r'(^|\s|/)(pytest|py\.test)(\s|$)|python(?:3)?\s+-m\s+pytest\b', re.I), 'unit', 'pytest'),
    (re.compile(r'\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test\b', re.I), 'unit', 'package test'),
    (re.compile(r'\b(?:go\s+test|cargo\s+test|unittest|vitest|jest)\b', re.I), 'unit', 'test runner'),
    (re.compile(r'\b(?:playwright|cypress)\b', re.I), 'e2e', 'browser test'),
    (re.compile(r'\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?build\b', re.I), 'build', 'package build'),
    (re.compile(r'\b(?:tsc|mypy|pyright)\b', re.I), 'typecheck', 'type checker'),
    (re.compile(r'\b(?:ruff|eslint|flake8)\b', re.I), 'lint', 'linter'),
)


def characterize(command: str) -> tuple[str, str]:
    if not isinstance(command, str) or not command.strip():
        return 'unknown', 'shell command [redacted]'
    for pattern, kind, label in CHECKS:
        if pattern.search(command):
            return kind, label + ' [arguments redacted]'
    return 'unknown', 'shell command [redacted]'


def parse_exit(value) -> int | None:
    if type(value) is int and -100000 <= value <= 100000:
        return value
    if isinstance(value, str):
        if re.fullmatch(r'-?\d{1,6}', value.strip()):
            return int(value.strip())
        match = EXIT.search(value[:15000])
        return int(match.group(1)) if match else None
    return None


def _command(raw):
    if isinstance(raw, list):
        # argv may contain secret options; never persist it.
        raw = ' '.join(str(part)[:2000] for part in raw[:24])
    return raw[:4096] if isinstance(raw, str) else None


def _claude_blocks(e):
    msg = e.get('message')
    return msg.get('content', []) if isinstance(msg, dict) and isinstance(msg.get('content'), list) else []


def _safe_str(x, max_len=12000):
    return x[:max_len] if isinstance(x, str) else ''


def _exit_from_claude_result(block, envelope):
    if isinstance(envelope, dict):
        for key in ('exitCode', 'exit_code', 'code'):
            if (code := parse_exit(envelope.get(key))) is not None:
                return code
    content = block.get('content')
    texts = [content] if isinstance(content, str) else (
        [b.get('text', '') for b in content[:10] if isinstance(b, dict) and b.get('type') == 'text']
        if isinstance(content, list) else [])
    return next((v for t in texts if (v := parse_exit(_safe_str(t))) is not None), None)


def _codex_command(payload):
    raw = payload.get('arguments') or payload.get('input')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw[:12000])
        except (ValueError, TypeError):
            return None
    if isinstance(raw, dict):
        return _command(raw.get('cmd') or raw.get('command'))
    return None


def _open_regular_nofollow(path: Path):
    """Reject symlink in final component, including replacement between check/open."""
    if path.suffix.lower() != '.jsonl':
        raise ValueError('Only explicitly selected .jsonl files are supported')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0)
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as ex:
        raise ValueError(f'Cannot open regular JSONL source: {type(ex).__name__}') from ex
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES or path.is_symlink():
            raise ValueError('Log must be a regular non-symlink file, <=256 MB')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


def import_log(root: Path, source_file: Path, provider: str = 'auto') -> dict:
    if provider not in ('auto', 'codex', 'claude'):
        raise ValueError('Provider must be codex, claude or auto')
    digest = hashlib.sha256()
    claude_pending, codex_pending = OrderedDict(), OrderedDict()
    observations: list[dict] = []
    truncated = malformed = ambiguous = 0
    counts = {'claude': 0, 'codex': 0}
    nbytes = 0

    def pending_set(pending, key, cmd, line):
        nonlocal ambiguous
        if not isinstance(key, str) or not key or cmd is None:
            return
        if len(pending) >= MAX_PENDING and key not in pending:
            pending.popitem(last=False)
            ambiguous += 1
        pending[key] = (cmd, line)

    def record(pending, key, code, line):
        if not isinstance(key, str) or key not in pending:
            return
        command, start = pending.pop(key)
        kind, preview = characterize(command)
        topic_tags = tags(command)
        if len(observations) >= MAX_OBSERVATIONS:
            raise ValueError('Too many command observations; split the log')
        observations.append({'record_key': key, 'line': start, 'end_line': line,
                             'check_kind_hint': kind, 'command_family': preview, 'topic_tags': topic_tags,
                             'log_exit_code': code})

    with _open_regular_nofollow(source_file) as fp:
        line_no = 0
        while True:
            line = fp.readline(MAX_LINE + 1)
            if not line:
                break
            line_no += 1
            if line_no > MAX_EVENTS:
                raise ValueError(f'Log exceeds {MAX_EVENTS} lines')
            nbytes += len(line)
            digest.update(line)
            oversize = len(line) > MAX_LINE
            if not line.endswith(b'\n'):
                # Consume an overlong physical line without loading it in memory.
                while True:
                    chunk = fp.readline(64 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    nbytes += len(chunk)
                    if nbytes > MAX_BYTES:
                        raise ValueError('Log exceeds 256 MB processing limit')
                    if chunk.endswith(b'\n'):
                        break
            if nbytes > MAX_BYTES:
                raise ValueError('Log exceeds 256 MB processing limit')
            if oversize:
                truncated += 1
                continue
            try:
                e = json.loads(line)
            except (UnicodeError, ValueError, RecursionError):
                malformed += 1
                continue
            if not isinstance(e, dict):
                continue
            t = e.get('type')
            if t in ('user', 'assistant') and isinstance(e.get('message'), dict):
                counts['claude'] += 1
                if t == 'assistant':
                    for block in _claude_blocks(e):
                        if isinstance(block, dict) and block.get('type') == 'tool_use' and block.get('name') == 'Bash':
                            args = block.get('input')
                            if isinstance(args, dict):
                                pending_set(claude_pending, block.get('id'), _command(args.get('command')), line_no)
                else:
                    for block in _claude_blocks(e):
                        if isinstance(block, dict) and block.get('type') == 'tool_result':
                            record(claude_pending, block.get('tool_use_id'),
                                   _exit_from_claude_result(block, e.get('toolUseResult')), line_no)
            elif t in ('response_item', 'event_msg', 'session_meta', 'item.started', 'item.completed', 'item.failed'):
                counts['codex'] += 1
                payload = e.get('payload')
                if t == 'response_item' and isinstance(payload, dict):
                    k = payload.get('type')
                    if k in ('function_call', 'custom_tool_call') and payload.get('name') in ('exec_command', 'functions.execute', 'shell_command'):
                        pending_set(codex_pending, payload.get('call_id'), _codex_command(payload), line_no)
                    elif k in ('function_call_output', 'custom_tool_call_output'):
                        code = parse_exit(payload.get('exit_code'))
                        if code is None:
                            code = parse_exit(_safe_str(payload.get('output')))
                        record(codex_pending, payload.get('call_id'), code, line_no)
                elif t == 'event_msg' and isinstance(payload, dict) and payload.get('type') == 'item_completed':
                    item = payload.get('item')
                    if isinstance(item, dict) and str(item.get('type', '')).lower() in ('commandexecution', 'command_execution'):
                        cmd = _command(item.get('command') or item.get('cmd'))
                        if cmd:
                            key = f'modern:{line_no}'
                            pending_set(codex_pending, key, cmd, line_no)
                            code = parse_exit(item.get('exit_code', item.get('exitCode')))
                            if code is None:
                                code = parse_exit(_safe_str(item.get('aggregated_output')))
                            record(codex_pending, key, code, line_no)
                elif t in ('item.started', 'item.completed', 'item.failed'):
                    item = e.get('item')
                    if isinstance(item, dict) and item.get('type') in ('command_execution', 'CommandExecution'):
                        key = str(item.get('id') or '')
                        cmd = _command(item.get('command') or item.get('cmd'))
                        if t == 'item.started':
                            pending_set(codex_pending, key, cmd, line_no)
                        else:
                            if key not in codex_pending and cmd:
                                pending_set(codex_pending, key or f'item:{line_no}', cmd, line_no)
                            code = parse_exit(item.get('exit_code', item.get('exitCode')))
                            # Failure event without an exit code is UNKNOWN rather than an invented OS exit.
                            record(codex_pending, key or f'item:{line_no}', code, line_no)

    if provider == 'auto':
        if (counts['codex'] > 0) == (counts['claude'] > 0):
            raise ValueError('Cannot uniquely infer provider; use --provider codex or claude')
        provider = 'codex' if counts['codex'] else 'claude'
    # Older legacy and modern Codex receipts may mirror one execution. Retain both
    # as observations rather than accidentally merging distinct repeated commands.
    saved = core.read_json(root / IMPORTS, {'schema': 1, 'observations': [], 'sources': []})
    if not isinstance(saved, dict) or not isinstance(saved.get('observations'), list):
        raise ValueError('Invalid existing imported evidence ledger')
    old = {r['id'] for r in saved['observations'] if isinstance(r, dict) and isinstance(r.get('id'), str)}
    source_digest = digest.hexdigest()
    added = []
    for row in observations:
        uid = 'A' + hashlib.sha256(f"{provider}:{source_digest}:{row['record_key']}:{row['line']}".encode()).hexdigest()[:12]
        if uid in old:
            continue
        added.append({'id': uid, 'provider': provider,
                      'command_family': row['command_family'], 'check_kind_hint': row['check_kind_hint'],
                      'topic_tags': row['topic_tags'],
                      'log_exit_code': row['log_exit_code'],
                      'log_status': 'RECORDED_ZERO' if row['log_exit_code'] == 0 else 'RECORDED_FAILURE' if row['log_exit_code'] is not None else 'UNKNOWN',
                      'source_digest': source_digest, 'source_name': '[explicit local JSONL file]',
                      'line': row['line'], 'end_line': row['end_line'],
                      'provenance': 'UNVERIFIED_AGENT_TRANSCRIPT', 'current_source_bound': False})
        old.add(uid)
    if len(saved['observations']) + len(added) > MAX_OBSERVATIONS:
        raise ValueError('Imported evidence store would exceed its 25,000-record limit')
    saved['observations'].extend(added)
    saved.setdefault('sources', []).append({'sha256': source_digest, 'provider': provider,
        'name': '[explicit local JSONL file]', 'skipped_oversize_lines': truncated,
        'skipped_malformed_lines': malformed, 'unmatched_pending_calls': len(claude_pending if provider == 'claude' else codex_pending),
        'evicted_pending_calls': ambiguous, 'no_raw_outputs_retained': True})
    core.write_json(root / IMPORTS, saved)
    return {'provider': provider, 'new_observations': len(added),
            'total_observations': len(saved['observations']),
            'unknown_exits': sum(r['log_exit_code'] is None for r in added),
            'skipped_oversize_lines': truncated, 'skipped_malformed_lines': malformed,
            'unmatched_pending_calls': len(claude_pending if provider == 'claude' else codex_pending),
            'note': 'Transcript is untrusted; imported records NEVER fulfill contracts.'}
