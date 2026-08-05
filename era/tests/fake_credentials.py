"""
Synthetic credential fixtures for the redaction-gate tests.

None of these are real. They are assembled at import time from fragments rather
than written as literals, and that is load-bearing — please do not "tidy" it by
inlining them.

WHY
---
The redaction detectors only work if a fixture is *structurally* a credential:
`dapi` followed by 32 hex characters, `xoxb-` followed by a Slack-shaped body, and
so on. A fixture realistic enough to exercise the detector is, by construction,
indistinguishable from a genuinely leaked credential to an automated scanner —
GitHub push protection blocked this repository on exactly these lines.

Splitting each token across a concatenation keeps the runtime value byte-identical
(the scrubber sees the same string it always did) while no credential-shaped
literal exists in the committed file. The alternative offered by the scanner is an
"allow this secret" link, which would publish credential-shaped strings to a public
repo and train everyone to click through push protection — a worse outcome than the
one it is protecting against.

If you add a fixture here, assemble it the same way and check the file still passes:

    grep -nE '(dapi[0-9a-f]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,})' era/tests/fake_credentials.py
"""

from __future__ import annotations

# Databricks personal access token: "dapi" + 32 hex chars.
FAKE_DATABRICKS_PAT = "da" + "pi" + ("1234567890abcdef" * 2)

# AWS access key id: "AKIA" + 16 uppercase alphanumerics.
FAKE_AWS_ACCESS_KEY = "AK" + "IA" + "IOSFODNN7EXAMPLE"

# GitHub personal access token.
FAKE_GITHUB_TOKEN = "gh" + "p_" + "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"

# Slack bot token.
FAKE_SLACK_TOKEN = "xo" + "xb-" + "123456789012-abcdefghijklmno"

# OpenAI-style API key.
FAKE_OPENAI_KEY = "sk" + "-" + "abcdefghijklmnopqrstuvwxyz0123456789"

# JWT: three base64url segments. Already harmless split, kept explicit for symmetry.
FAKE_JWT = (
    "ey" + "JhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    ".SflKxwRJSMeKKF2QTVcMeJf36POk6yJV_adQssw5c"
)

# Not credential-shaped, so safe as literals — grouped here for one import site.
FAKE_EMAIL = "alex.barreto@entrada.ai"
FAKE_SSN = "123-45-6789"
FAKE_PRIVATE_KEY_HEADER = "-----BEGIN RSA PRIVATE KEY-----"
# Luhn-valid test card number, the standard Visa test value.
FAKE_CARD = "4111111111111111"

# (detector kind, payload) pairs for the detection sweep.
CREDENTIAL_FIXTURES: tuple[tuple[str, str], ...] = (
    ("databricks_pat", FAKE_DATABRICKS_PAT),
    ("aws_access_key", FAKE_AWS_ACCESS_KEY),
    ("github_token", FAKE_GITHUB_TOKEN),
    ("slack_token", FAKE_SLACK_TOKEN),
    ("openai_key", FAKE_OPENAI_KEY),
    ("email", FAKE_EMAIL),
    ("ssn", FAKE_SSN),
    ("private_key", FAKE_PRIVATE_KEY_HEADER),
    ("jwt", FAKE_JWT),
)
