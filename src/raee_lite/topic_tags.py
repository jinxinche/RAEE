"""Small, fixed, privacy-conscious vocabulary for optional relevance hints.

No arbitrary words from commands or transcripts are persisted. Empty tag overlap
means no automated suggestion. A matching topic is never proof of coverage.
"""
from __future__ import annotations
import re

TOPICS = (
    'login', 'signup', 'register', 'checkout', 'payment', 'billing', 'oauth',
    'auth', 'database', 'migration', 'deploy', 'docker', 'startup', 'security',
    'permission', 'secret', 'api', 'webhook', 'email', 'upload', 'download',
    'cache', 'search', 'css', 'layout', 'notification', 'password', 'session',
    'token', 'lint', 'typecheck',
)
PATTERNS = {t: re.compile(r'(?<![a-z0-9])' + re.escape(t) + r'(?![a-z0-9])', re.I) for t in TOPICS}
ALIASES = {'sign-in':'login', 'sign in':'login', 'log in':'login', 'sign up':'signup',
           'db':'database', 'payments':'payment', 'tests_login':'login'}


def tags(text):
    if not isinstance(text, str):
        return []
    text = text[:4096].casefold()
    matches = {t for t, rgx in PATTERNS.items() if rgx.search(text)}
    matches.update(target for phrase,target in ALIASES.items() if phrase in text)
    return sorted(matches)
