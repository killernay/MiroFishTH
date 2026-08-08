# Ubiquitous Language

## Locale and content

- **Interface locale**: The English or Thai language selected for the user interface.
- **Project locale**: The locale captured when a project begins. It governs system-generated content before a simulation run exists.
- **Run locale**: The immutable English or Thai locale captured when a simulation run is created. Workers, retries, logs, reports, and generated simulation content use it for that run.
- **Generated content**: Any user-visible text produced by MiroFish or its models, including UI copy, status messages, logs, personas, simulation posts, reports, chats, and exports. It must use the project or run locale.
- **Quoted source evidence**: Text supplied by uploaded source material or preserved verbatim as evidence. It is not translated automatically; the UI and exports label it as quoted source evidence in the active interface locale.
- **Legacy artifact**: A report or run created before locale persistence. Its content is preserved and is not translated automatically.

## Remote access

- **Office host**: The work machine that runs MiroFish continuously in Docker.
- **Private remote access**: Access to the office host only through the user's Tailscale tailnet; it is not a public internet service.
- **Production container**: A non-development MiroFish container with restart policy and persistent volumes suitable for the office host.
- **Direct tailnet endpoint**: The office host's known Tailscale IP and a single exposed HTTP port; it is not exposed through Tailscale Serve or the public internet.
- **Same-origin gateway**: The production reverse proxy that serves the frontend at the direct tailnet endpoint and routes `/api/` to the internal backend, avoiding browser CORS and remote `localhost` failures.
- **Access password**: HTTP Basic Auth configured through environment secrets at the same-origin gateway; it is an additional gate for private remote access, not an application account system.
