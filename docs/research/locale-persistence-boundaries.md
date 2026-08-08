# Locale persistence boundaries

## Question

Where must project and run locale be stored and read so an English or Thai
selection remains deterministic through graph building, preparation, execution,
reporting, chat, and retries?

## Findings

### Current locale is request/thread scoped, not durable

- The frontend stores a selected locale in browser `localStorage` and sends it
  as `Accept-Language` for every API request
  ([frontend/src/i18n/index.js:17-20](../../frontend/src/i18n/index.js),
  [frontend/src/api/index.js:14-17](../../frontend/src/api/index.js)). This
  means a later request reflects the current UI language, rather than the
  language selected when an artifact was created.
- Backend normalization permits only a locale present in both `languages.json`
  and translations, otherwise returning English; its getter reads the request
  header when one exists and only otherwise uses thread-local state
  ([backend/app/utils/locale.py:24-39](../../backend/app/utils/locale.py)).
  This is a sound validation boundary but no persisted ownership boundary.
- Background graph, preparation, report, monitor, and Zep-updater workers copy
  the request locale into a thread-local before starting their work
  ([backend/app/services/graph_builder.py:108-133](../../backend/app/services/graph_builder.py),
  [backend/app/api/simulation.py:534-545](../../backend/app/api/simulation.py),
  [backend/app/api/report.py:242-247](../../backend/app/api/report.py),
  [backend/app/services/simulation_runner.py:580-651](../../backend/app/services/simulation_runner.py),
  [backend/app/services/zep_graph_memory_updater.py:300-412](../../backend/app/services/zep_graph_memory_updater.py)).
  Therefore a refresh, retry, process restart, or different API request can
  choose a different language.

### Project-locale persistence seam

- `Project` is the durable project record, serialized as
  `uploads/projects/<project_id>/project.json`; its `to_dict` and `from_dict`
  are the backward-compatible schema boundary
  ([backend/app/models/project.py:22-103](../../backend/app/models/project.py),
  [backend/app/models/project.py:124-197](../../backend/app/models/project.py)).
- The upload/ontology endpoint creates the project and immediately generates
  project-owned generated content (ontology and `analysis_summary`), but it
  does not capture `get_locale()` or accept a locale field
  ([backend/app/api/graph.py:316-380](../../backend/app/api/graph.py)).
- Graph construction uses the ephemeral request locale passed to its worker,
  rather than a field on the project
  ([backend/app/api/graph.py:647-665](../../backend/app/api/graph.py)).

**Concrete seam:** add a normalized `locale` (or explicitly named
`project_locale`) field to `Project`, serialize/deserialize it with a default
of `en` for records without the field, and set it once at project creation.
Graph build/rebuild workers should resolve their locale from the loaded project,
not `Accept-Language`.

### Run-locale persistence seam

- The system's durable simulation identity spans preparation and execution:
  `SimulationState` is stored at
  `uploads/simulations/<simulation_id>/state.json`
  ([backend/app/services/simulation_manager.py:35-118](../../backend/app/services/simulation_manager.py),
  [backend/app/services/simulation_manager.py:152-205](../../backend/app/services/simulation_manager.py)).
- Creating that state has the project available but currently stores no locale
  ([backend/app/api/simulation.py:227-258](../../backend/app/api/simulation.py),
  [backend/app/services/simulation_manager.py:210-243](../../backend/app/services/simulation_manager.py)).
- Preparation starts an LLM profile/config pipeline in a thread using the
  request header locale, while a subsequent `force_regenerate` can invoke the
  same pipeline under a new request language
  ([backend/app/api/simulation.py:455-545](../../backend/app/api/simulation.py),
  [backend/app/services/simulation_manager.py:276-465](../../backend/app/services/simulation_manager.py)).
- `SimulationRunState` is a second durable projection at `run_state.json`, but
  it also has no locale field and is newly constructed by `start_simulation`
  ([backend/app/services/simulation_runner.py:110-200](../../backend/app/services/simulation_runner.py),
  [backend/app/services/simulation_runner.py:330-397](../../backend/app/services/simulation_runner.py),
  [backend/app/services/simulation_runner.py:402-455](../../backend/app/services/simulation_runner.py)).

**Concrete seam:** copy the already-normalized project locale into an immutable
`locale` on `SimulationState` when `/create` creates the simulation. Use that
field for all preparation/forced-regeneration workers. Copy the same value into
`SimulationRunState` when execution begins (or derive it from `SimulationState`
after load) so monitor/recovery code has an independent durable read. Missing
locale in either legacy state file must deserialize as `en`, without rewriting
existing report/simulation content.

### Process and report boundaries

- `SimulationRunner` passes only configuration path and UTF-8 environment to
  the OASIS subprocess; it does not pass the locale to its child process
  ([backend/app/services/simulation_runner.py:535-585](../../backend/app/services/simulation_runner.py)).
  The scripts load only the configuration and use LLM-backed actions
  ([backend/scripts/run_parallel_simulation.py:604-650](../../backend/scripts/run_parallel_simulation.py),
  [backend/scripts/run_parallel_simulation.py:984-1033](../../backend/scripts/run_parallel_simulation.py)).
  A persistent `locale` must therefore be written into `simulation_config.json`
  and/or passed as a dedicated environment/CLI value, then consumed in the
  subprocess's LLM prompts. Thread-local backend locale cannot cross this
  process boundary.
- Report metadata, outline, markdown, and logs are persisted, but `Report` and
  `ReportManager` contain no locale field
  ([backend/app/services/report_agent.py:442-475](../../backend/app/services/report_agent.py),
  [backend/app/services/report_agent.py:1931-2005](../../backend/app/services/report_agent.py),
  [backend/app/services/report_agent.py:2474-2545](../../backend/app/services/report_agent.py)).
  Report generation captures the request locale, including when
  `force_regenerate` requests a fresh report
  ([backend/app/api/report.py:214-272](../../backend/app/api/report.py)).
- Report chat similarly creates an agent based on a simulation but does not
  set the locale from persisted simulation state
  ([backend/app/api/report.py:621-685](../../backend/app/api/report.py)).

**Concrete seam:** resolve report-generation and report-chat locale from
`SimulationState.locale`, never the caller's header. Store `locale` with the
new `Report` artifact so display/export can distinguish legacy artifacts and
quoted-source labels reliably. `force_regenerate` must preserve the simulation
locale. Existing reports with no field remain legacy and are served unchanged.

## Migration and validation implications

- Normalization already makes unsupported and legacy `zh` resolve to `en`
  ([backend/app/utils/locale.py:24-29](../../backend/app/utils/locale.py));
  the migration should apply that function when loading legacy persisted values
  and use `en` when the key is absent.
- The frontend's current stale-local-storage fallback occurs in the i18n module
  ([frontend/src/i18n/index.js:17-20](../../frontend/src/i18n/index.js)). It
  should overwrite a stored unsupported/`zh` value with `en`, rather than only
  falling back in memory.
- Testing needs restart-oriented fixtures: create a Thai project, reload its
  JSON with a different request locale, then assert graph build, prepare,
  start/recovery, report generation, and report chat each use Thai. Repeat for
  English and missing/`zh` legacy JSON (English). Verify no migration mutates
  pre-existing report markdown or source-evidence text.

## Remaining decision points

1. Decide whether the duplicate `SimulationRunState.locale` is mandatory
   schema redundancy (recommended for recovery isolation) or merely a cached
   copy always reconstructed from `SimulationState`. Both preserve the chosen
   immutable run locale; the former makes `run_state.json` self-describing.
2. Decide the subprocess contract: `simulation_config.json` is the preferred
   durable/replayable carrier, but its OASIS action layer must expose a prompt
   injection point for locale. If it does not, an environment variable is also
   required. This needs a focused trace of the vendored OASIS prompt path.
3. Decide whether report chat is considered generated run content (recommended:
   yes, so it is pinned to run locale) even when the UI locale has since
   changed; interface chrome and quoted-source labels can still follow the
   current UI locale.
