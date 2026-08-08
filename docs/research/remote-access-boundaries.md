# Remote-access boundary findings

## Question

Can an office-hosted MiroFish Docker container be used from another device via
the office host's Tailscale IP, and what currently prevents it?

## Verdict

The verified primary failure is a browser-local endpoint, not backend CORS:
the browser is hard-coded to call `http://localhost:5001`.  From a remote
device, `localhost` is that remote device, so its request never reaches the
office host.  The current container publishes both application ports on all
host interfaces, and Flask is configured to accept cross-origin `/api/*`
requests.  Direct access by Tailscale IP is therefore viable once the API URL
is made origin-relative or explicitly points to the office host.

## Evidence

| Boundary | Local evidence | Consequence |
| --- | --- | --- |
| Browser to API | [`frontend/src/api/index.js:5-10`](../../frontend/src/api/index.js) sets Axios `baseURL` to `VITE_API_BASE_URL` or `http://localhost:5001`. | With no `VITE_API_BASE_URL`, a browser on a home device calls port 5001 on the home device, not the office host. |
| Development proxy | [`frontend/vite.config.js:14-23`](../../frontend/vite.config.js) proxies only paths beginning `/api` to `localhost:5001` inside the Vite process. | It cannot help while Axios uses an absolute `http://localhost:5001` URL; it would help if the frontend used relative `/api` URLs. |
| Backend listener | [`backend/run.py:39-45`](../../backend/run.py) defaults Flask to `0.0.0.0:5001`. | Flask accepts requests arriving at the container's network interface. |
| CORS | [`backend/app/__init__.py:42-43`](../../backend/app/__init__.py) enables CORS for `/api/*` with `origins: "*"`. | A correctly-addressed cross-origin browser request is not rejected by the application's CORS policy. This is broad for production, but it is not the observed blocker. |
| Docker publication | [`docker-compose.yml:9-12`](../../docker-compose.yml) publishes `3000` and `5001` and uses `restart: unless-stopped`. | Compose's default host binding exposes both ports beyond loopback; Docker inspection of the currently running `mirofishth` confirms `0.0.0.0` and IPv6 `::` bindings for host ports `3410 -> 3000` and `5101 -> 5001`. |
| Current runtime | [`Dockerfile:26-29`](../../Dockerfile) exposes both ports and starts `npm run dev`; [`package.json:7-10`](../../package.json) defines that as concurrent backend plus frontend development servers. | The deployed image is a development-server topology, not a production web-server topology. |
| Vite host validation | [`frontend/package.json:6-10`](../../frontend/package.json) runs `vite --host`; installed Vite accepts IPv4/IPv6 Host headers directly (`frontend/node_modules/vite/dist/node/chunks/config.js:20350-20356`). | An IP-form Tailscale URL is not blocked by Vite's allowed-host check. A tailnet DNS hostname could require an explicit `server.allowedHosts` entry. |

### Runtime checks performed

- `http://127.0.0.1:3410/` returned HTTP 200 from the current `mirofishth`
  container.
- `http://127.0.0.1:5101/health` returned HTTP 200.
- Sending an IPv4-style `Host` header to the Vite port also returned HTTP 200;
  this matches Vite's local implementation, which permits IP host headers.

These checks establish that both published services are alive locally. They do
not prove the office host's Tailscale firewall/ACL or host sleep state.

## Direct Tailscale-IP deployment options

### A. Transitional two-port access

Set `VITE_API_BASE_URL` at frontend build/start time to the stable office
Tailscale API URL, for example `http://<office-tailscale-ip>:5101`, and open
the UI at `http://<office-tailscale-ip>:3410`.

- Works with the current Flask CORS setting.
- Requires publishing and protecting two ports.
- Bakes the IP into a production frontend build, so an IP change requires a
  rebuild/restart.
- Is acceptable only inside the tailnet; it should not be exposed publicly.

### B. Recommended single-origin production topology

Build the Vue frontend once and serve it behind a production reverse proxy on
one Tailscale-reachable port. Route `/api/` from that same origin to Flask,
and make Axios use a relative base URL (`/api`). Keep Flask un-published to
the host, reachable only by the proxy's Docker network.

- The browser uses `http://<office-tailscale-ip>:<port>/api/...`, eliminating
  both `localhost` ambiguity and CORS from the browser boundary.
- The proxy is the right place for the requested simple HTTP Basic Auth; the
  service remains reachable only through the tailnet.
- Use a `restart: unless-stopped` policy and mount the whole
  `backend/uploads` tree. This is already the persisted state root: see
  [`backend/app/config.py:35-46`](../../backend/app/config.py). The existing
  Compose file already mounts it at
  [`docker-compose.yml:13-14`](../../docker-compose.yml).

## Decision implications

1. Do not diagnose this as a CORS-only problem. Fix the frontend endpoint
   selection first.
2. Treat the current Vite process as development-only. A production container
   should serve static assets and proxy the API under one origin.
3. Tailscale IP access needs no Tailscale Serve. It does require the office
   host to remain awake, Docker to be running, and tailnet ACLs/firewall rules
   to allow the chosen UI port.
