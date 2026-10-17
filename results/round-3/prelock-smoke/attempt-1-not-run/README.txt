Attempt 1 (2026-10-15T17:20:43Z-17:20:45Z) ran uv sync only.
The script called `env`, which on this host resolves to uv's PATH helper (~/.local/bin/env, a shell script that ignores its arguments), so pytest and both smoke runs never started: no test ran, no model was called, no receipt was written.
The exit codes 0 in session.txt are the helper's, not pytest's or smoke.py's. Attempt 2 calls /usr/bin/env.
