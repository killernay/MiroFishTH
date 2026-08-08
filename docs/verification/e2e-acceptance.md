# Bilingual and private-access acceptance

## Automated checks

| Capability | Verification | Expected result |
| --- | --- | --- |
| English and Thai UI | `frontend/test/process-locale.test.mjs` and production build | Only English or Thai interface copy; legacy browser `zh` falls back to English. |
| Generated content | `backend/tests/test_generation_language.py` | Generated text outside an evidence block is English or Thai, retries once on a violation, then fails clearly. |
| Quoted source evidence | Report/chat evidence tests | Only text found in a live server tool result can be preserved verbatim; it is rendered in a labelled fenced block. |
| Legacy artifacts | Locale persistence tests | Missing or `zh` locale resolves to English without rewriting stored artifacts. |
| Same-origin access | `tests/test_remote_access_contract.py` | Browser uses relative `/api`; Caddy publishes one Basic-Auth-protected port and keeps Gunicorn private. |
| Restart recovery | `backend/uploads` bind mount plus the procedure below | Projects, runs, and reports remain on disk after container recreation. |

## Office-host check

1. Run `tailscale ip -4` and set that value as `TAILSCALE_IP` in the ignored `.env`.
2. Run `docker compose up -d --build`.
3. Confirm an unauthenticated request to `http://<TAILSCALE_IP>:3410/` returns `401`.
4. Authenticate at the same URL and create a new English or Thai project. Create a run and a report.
5. Run `docker compose restart`, authenticate again, and confirm the project/report still appear.

## Second-device acceptance

From another device enrolled in the same Tailscale tailnet, open
`http://<TAILSCALE_IP>:3410/` and authenticate. Confirm the application loads,
creates an API request under the same origin, and does not call that device's
`localhost`. Repeat the restart recovery step above from that device.

This final check requires a real second tailnet device; it cannot be proven by
the office host alone.
