# 0.0 — reviewer-deepseek — round 0

Verdict: approve

## Findings

### F1 — nit
- Where: test/pytest/conftest.py:19-22 (docstring), 35 (`random.randrange(20_000, 40_000)`)
- What: The fixture docstring claims the chosen range is "deliberately outside the OS ephemeral port range", but 20000-40000 overlaps the Linux ephemeral range (which starts at 32768).
- Why: The claim is factually wrong on Linux, where 32768-40000 is inside the OS's ephemeral allocation. The real protection is the bind-check of both ports before returning, which is sound; the docstring just misstates it.
- Suggested fix: Rephrase the docstring to say the range is wide and random and that both ports are verified free by binding them before returning (drop the "outside the ephemeral range" claim, or pick a range truly below Linux's 32768 lower bound).

### F2 — nit
- Where: test/pytest/test_server_gui.py:25-29
- What: `_wait_until_client_points_at_server` duplicates the wait-for-client-retarget guard already in `test_gui_navigation._start_window` (test/pytest/test_gui_navigation.py:37-42).
- Why: Two copies of the same timing logic; latent drift risk if the client retarget behaviour changes.
- Suggested fix: Optional — factor into a shared helper in conftest.py, or leave; it is correct as written.

## Notes

- Acceptance grep is satisfied: `grep -rn "5555\|5599" test/pytest` returns nothing (remaining 5555/5599 literals elsewhere in test/ are outside test/pytest, in the not-pytest integration scripts, notebooks, a docs-verification helper comment, and test_config.py config-string assertions — all out of this task's scope and none bound a live port).
- test_apps.py now asserts the launcher default via `instrumentserver.DEFAULT_PORT`, so the 5555 literal is gone without any src/ change, as the orchestrator instructed.
- Tests I ran (whole suite): `uv run pytest -q` → `161 passed, 4 warnings in 58.80s`. The 4 warnings are a pre-existing unknown-mark warning for `pytest.mark.integration` in test_apps.py, unrelated to this change.
- Parallel acceptance check: two concurrent `uv run pytest` runs over test_basic_functionality.py + test_client_station.py both passed (16 passed each), confirming the per-session port pair prevents collision.
- The server_port fixture bind-checks both `port` and `port+1` before returning, and the shutdown client in `start_server` now uses the same server_port; `server_port` is session-scoped so every consumer in a session agrees on one port pair.
- No must-fix or should-fix findings.