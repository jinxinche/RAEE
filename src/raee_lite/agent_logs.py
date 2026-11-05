"""Streaming, untrusted Codex/Claude transcript importer.

Only coarse command family and exit-code metadata leave the parser. Never treats
agent-owned assertions or transcript output as independently verified tests.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from collections import OrderedDict
from pathlib import Path

from . import core
from .safe_io import strict_json_loads
from .topic_tags import tags

IMPORTS = Path('.raee/imports.json')
MAX_LINE = 512_000
MAX_BYTES = 256_000_000
MAX_EVENTS = 200_000
MAX_PENDING = 2048
MAX_OBSERVATIONS = 25_000
EXIT = re.compile(r'(?im)^\s*(?:Process exited with code|Exit code|Process exit code)\s*:?\s*(-?\d{1,6})\s*$')
RUNNING = re.compile(r'Process running with session ID ([A-Za-z0-9_-]+)', re.I)
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


def _exit_value(value) -> int | None:
    if type(value) is int and -100000 <= value <= 100000:
        return value
    if isinstance(value, str) and re.fullmatch(r'-?[0-9]{1,6}', value.strip()):
        code = int(value.strip())
        return code if -100000 <= code <= 100000 else None
    return None


def _metadata_exit(value):
    codes = [_exit_value(value[key]) for key in ('exit_code', 'exitCode', 'code') if key in value]
    return codes[0] if codes and None not in codes and len(set(codes)) == 1 else None


def _session_id(value):
    if type(value) is int and value >= 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        return value
    return None


def _wrapper_result(value, *, structured=True):
    """Read only structured metadata or the leading provider wrapper, never stdout."""
    if isinstance(value, str):
        value = value[:12000].strip()
        if structured and value.startswith('{'):
            value = strict_json_loads(value)
    if isinstance(value, dict):
        session = _session_id(value.get('session_id'))
        return (None if session else _metadata_exit(value)), session
    if not isinstance(value, str):
        return None, None
    codes, sessions = [], []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        if match := EXIT.fullmatch(line):
            codes.append(_exit_value(match.group(1)))
        elif match := RUNNING.fullmatch(line):
            sessions.append(match.group(1))
        elif re.fullmatch(r'(?:Chunk ID|Wall time|Original token count):[^\r\n]*', line, re.I):
            continue
        else:
            # Output:/Final output: and the first body line end the metadata.
            break
    if sessions:
        if len(set(sessions)) != 1:
            raise ValueError('Ambiguous running session metadata')
        return None, sessions[0]
    return (codes[0] if len(codes) == 1 else None), None


def parse_exit(value) -> int | None:
    """Compatibility helper; bare numeric values are metadata only, not output."""
    code = _exit_value(value)
    return code if code is not None else _wrapper_result(value)[0]


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
    if isinstance(envelope, dict) and any(key in envelope for key in ('exitCode', 'exit_code', 'code')):
        code = _metadata_exit(envelope)
        return None if code == 0 and block.get('is_error') else code
    content = block.get('content')
    texts = [content] if isinstance(content, str) else (
        [b.get('text', '') for b in content[:10] if isinstance(b, dict) and b.get('type') == 'text']
        if isinstance(content, list) else [])
    # Multiple text blocks have no unambiguous wrapper boundary.
    code = _wrapper_result(_safe_str(texts[0]), structured=False)[0] if len(texts) == 1 else None
    return None if code == 0 and block.get('is_error') else code


def _codex_arguments(payload):
    raw = payload.get('arguments') or payload.get('input')
    if isinstance(raw, str):
        raw = strict_json_loads(raw[:12000])
    return raw if isinstance(raw, dict) else {}


def _codex_result(payload):
    if any(key in payload for key in ('exit_code', 'exitCode', 'code')):
        code = _metadata_exit(payload)
        # Invalid/absent status must not erase an explicit running wrapper.
        session = _wrapper_result(payload.get('output'))[1] if code is None else None
    else:
        code, session = _wrapper_result(payload.get('output'))
    session = _session_id(payload.get('session_id')) or session
    return (None if session else code), session


def _open_regular_nofollow(path: Path):
    """Reject symlink in final component, including replacement between check/open."""
    if path.suffix.lower() != '.jsonl':
        raise ValueError('Only explicitly selected .jsonl files are supported')
    from .safe_io import _reject_links
    _reject_links(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
        raise ValueError('Log must be a bounded regular file')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0)
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as ex:
        raise ValueError(f'Cannot open regular JSONL source: {type(ex).__name__}') from ex
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES or path.is_symlink() or
                (st.st_dev, st.st_ino) != (before.st_dev, before.st_ino)):
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
    sessions, polls = {}, {}
    seen_calls = {'claude': set(), 'codex': set()}
    observations: list[dict] = []
    truncated = malformed = evicted = 0
    counts = {'claude': 0, 'codex': 0}
    nbytes = 0

    def remember_call(pending, key):
        seen = seen_calls['claude' if pending is claude_pending else 'codex']
        if key in seen:
            raise ValueError('Duplicate tool call ID')
        if len(seen) >= MAX_EVENTS:
            raise ValueError('Too many tool call IDs; split the log')
        seen.add(key)

    def pending_set(pending, key, cmd, line):
        nonlocal evicted
        if not isinstance(key, str) or not key or cmd is None:
            return
        # Remember retired/evicted IDs too: a late result must never bind a new call.
        remember_call(pending, key)
        if len(pending) >= MAX_PENDING:
            dropped, _ = pending.popitem(last=False)
            if pending is codex_pending:
                forget_session(dropped)
            evicted += 1
        pending[key] = (cmd, line, line)

    def forget_session(key):
        for session, original in list(sessions.items()):
            if original == key:
                del sessions[session]
        for poll, original in list(polls.items()):
            if original == key:
                del polls[poll]

    def record(pending, key, code, line, *, incomplete=False):
        if not isinstance(key, str) or key not in pending:
            return
        command, start, last = pending.pop(key)
        if pending is codex_pending:
            forget_session(key)
        kind, preview = characterize(command)
        topic_tags = tags(command)
        if len(observations) >= MAX_OBSERVATIONS:
            raise ValueError('Too many command observations; split the log')
        observations.append({'record_key': key, 'line': start, 'end_line': last if incomplete else line,
                             'provider': 'claude' if pending is claude_pending else 'codex',
                             'incomplete': incomplete,
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
                e = strict_json_loads(line)
            except (UnicodeError, ValueError, RecursionError):
                malformed += 1
                continue
            if not isinstance(e, dict):
                malformed += 1
                continue
            t = e.get('type')
            if t in ('user', 'assistant') and isinstance(e.get('message'), dict):
                counts['claude'] += 1
                if provider not in ('auto', 'claude'):
                    continue
                if t == 'assistant':
                    for block in _claude_blocks(e):
                        if isinstance(block, dict) and block.get('type') == 'tool_use' and block.get('name') == 'Bash':
                            args = block.get('input')
                            if isinstance(args, dict):
                                pending_set(claude_pending, block.get('id'), _command(args.get('command')), line_no)
                else:
                    for block in _claude_blocks(e):
                        if isinstance(block, dict) and block.get('type') == 'tool_result':
                            try:
                                code = _exit_from_claude_result(block, e.get('toolUseResult'))
                            except ValueError:
                                malformed += 1
                                continue
                            record(claude_pending, block.get('tool_use_id'), code, line_no)
            elif t in ('response_item', 'event_msg', 'session_meta', 'item.started', 'item.completed', 'item.failed'):
                counts['codex'] += 1
                if provider not in ('auto', 'codex'):
                    continue
                payload = e.get('payload')
                if t == 'response_item' and isinstance(payload, dict):
                    k = payload.get('type')
                    if k in ('function_call', 'custom_tool_call') and payload.get('name') in (
                            'exec_command', 'functions.execute', 'shell_command', 'write_stdin', 'functions.write_stdin'):
                        try:
                            args = _codex_arguments(payload)
                        except ValueError:
                            malformed += 1
                            continue
                        key = payload.get('call_id')
                        if payload.get('name') in ('write_stdin', 'functions.write_stdin'):
                            original = sessions.get(_session_id(args.get('session_id')))
                            if isinstance(key, str) and key and original in codex_pending:
                                remember_call(codex_pending, key)
                                if len(polls) >= MAX_PENDING:
                                    raise ValueError('Too many pending session polls; split the log')
                                polls[key] = original
                        else:
                            pending_set(codex_pending, key, _command(args.get('cmd') or args.get('command')), line_no)
                    elif k in ('function_call_output', 'custom_tool_call_output'):
                        key = payload.get('call_id')
                        if not isinstance(key, str):
                            continue
                        try:
                            code, session = _codex_result(payload)
                        except ValueError:
                            malformed += 1
                            continue
                        key = polls.pop(key, key)
                        if key not in codex_pending:
                            continue
                        if session or (code is None and key in sessions.values()):
                            if session:
                                if session in sessions and sessions[session] != key:
                                    raise ValueError('Ambiguous running session ID')
                                if key in sessions.values() and sessions.get(session) != key:
                                    raise ValueError('Running session ID changed')
                                sessions[session] = key
                            cmd, start, _ = codex_pending[key]
                            codex_pending[key] = (cmd, start, line_no)
                        else:
                            record(codex_pending, key, code, line_no)
                elif t == 'event_msg' and isinstance(payload, dict) and payload.get('type') == 'item_completed':
                    item = payload.get('item')
                    if isinstance(item, dict) and str(item.get('type', '')).lower() in ('commandexecution', 'command_execution'):
                        cmd = _command(item.get('command') or item.get('cmd'))
                        if cmd:
                            key = f'modern:{line_no}'
                            pending_set(codex_pending, key, cmd, line_no)
                            code = _metadata_exit(item)
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
                            code = _metadata_exit(item)
                            # Failure event without an exit code is UNKNOWN rather than an invented OS exit.
                            record(codex_pending, key or f'item:{line_no}', code, line_no)

    if provider == 'auto':
        if (counts['codex'] > 0) == (counts['claude'] > 0):
            raise ValueError('Cannot uniquely infer provider; use --provider codex or claude')
        provider = 'codex' if counts['codex'] else 'claude'
    elif not counts[provider] and any(counts.values()):
        raise ValueError('Selected provider does not match transcript events')
    # Keep incomplete executions visible, including calls that never returned.
    unmatched = len(claude_pending) + len(codex_pending) + evicted
    for pending in (claude_pending, codex_pending):
        for key in list(pending):
            record(pending, key, None, line_no, incomplete=True)
    # Older legacy and modern Codex receipts may mirror one execution. Retain both
    # as observations rather than accidentally merging distinct repeated commands.
    saved = core.read_json(root / IMPORTS, {'schema': 1, 'observations': [], 'sources': []})
    if not isinstance(saved, dict) or not isinstance(saved.get('observations'), list):
        raise ValueError('Invalid existing imported evidence ledger')
    old = {r['id'] for r in saved['observations'] if isinstance(r, dict) and isinstance(r.get('id'), str)}
    source_digest = digest.hexdigest()
    added = []
    for row in observations:
        uid = 'A' + hashlib.sha256(f"{row['provider']}:{source_digest}:{row['record_key']}:{row['line']}".encode()).hexdigest()[:12]
        if uid in old:
            continue
        added.append({'id': uid, 'provider': row['provider'], 'incomplete': row['incomplete'],
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
        'skipped_malformed_lines': malformed, 'unmatched_pending_calls': unmatched,
        'evicted_pending_calls': evicted, 'no_raw_outputs_retained': True})
    core.write_json(root / IMPORTS, saved)
    return {'provider': provider, 'new_observations': len(added),
            'total_observations': len(saved['observations']),
            'unknown_exits': sum(r['log_exit_code'] is None for r in added),
            'skipped_oversize_lines': truncated, 'skipped_malformed_lines': malformed,
            'unmatched_pending_calls': unmatched, 'evicted_pending_calls': evicted,
            'note': 'Transcript is untrusted; imported records NEVER fulfill contracts.'}
