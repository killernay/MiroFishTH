# English/Thai Presentation Boundaries

## Scope and method

This is a read-only inventory of primary local source code. “User-visible” includes browser copy, API task/status strings rendered by the browser, generated artefacts, report/chat/tool text, and simulation/report log files exposed by the product. It does **not** treat uploaded source text as a defect: source excerpts must remain verbatim and be labelled in the active interface locale.

## Current language architecture

- The front end loads every `locales/*.json` whose key exists in the registry. It accepts a saved `localStorage.locale` when it is both registered and loaded; only an invalid saved value falls back to English. [frontend/src/i18n/index.js:4-25](../../frontend/src/i18n/index.js)
- The registry itself contains only `en` and `th`, and its two LLM instructions correctly prohibit Chinese. [locales/languages.json:1-10](../../locales/languages.json) The front-end guard consequently excludes the checked-in `zh.json` from browser messages. The backend loader still reads every catalog file but locale normalization rejects keys absent from the registry. [backend/app/utils/locale.py:15-29](../../backend/app/utils/locale.py) Keeping `zh.json` is misleading dead state and makes future regressions easier, but it is not currently selectable by this code path.
- Thai browser translations are absent: `locales/th.json` is `{}`. Vue I18n therefore falls back to English for every missing key, rather than providing a Thai UI. [locales/th.json:1](../../locales/th.json), [frontend/src/i18n/index.js:22-27](../../frontend/src/i18n/index.js)
- Back-end locale selection is request/thread-local, derived from `Accept-Language`; it has no persisted project or run field. Background work captures the current request locale and restores it in its worker thread. [backend/app/utils/locale.py:24-39](../../backend/app/utils/locale.py), [backend/app/api/graph.py:647-652](../../backend/app/api/graph.py), [backend/app/api/simulation.py:534-539](../../backend/app/api/simulation.py)
- `Project` serialization has no locale property, and `SimulationState` is likewise the current natural storage seam for an immutable run locale. [backend/app/models/project.py:27-106](../../backend/app/models/project.py), [backend/app/services/simulation_manager.py:45-117](../../backend/app/services/simulation_manager.py)

## Confirmed Chinese presentation paths

### 1. Browser UI

| Surface | Evidence | Why it leaks |
| --- | --- | --- |
| Legacy graph-build process page | `Process.vue` hard-codes Chinese in nav, loading, graph/process panels, error states and next-step UI. [frontend/src/views/Process.vue:9-53](../../frontend/src/views/Process.vue), [frontend/src/views/Process.vue:167-249](../../frontend/src/views/Process.vue), [frontend/src/views/Process.vue:454-580](../../frontend/src/views/Process.vue), [frontend/src/views/Process.vue:799-945](../../frontend/src/views/Process.vue) | It does not import or call `useI18n`; the strings bypass locale files entirely. It also formats dates with `zh-CN`. [frontend/src/views/Process.vue:501-512](../../frontend/src/views/Process.vue) |
| Saved locale migration | The switcher writes an arbitrary selected key directly to local storage. [frontend/src/components/LanguageSwitcher.vue:39-55](../../frontend/src/components/LanguageSwitcher.vue) | A one-time normalization of existing `zh` storage is required in i18n bootstrapping, not only a selector change. |
| Date/time formatting | Multiple active views force `en-US`; the legacy process page forces `zh-CN`. Examples: [frontend/src/components/Step1GraphBuild.vue:262](../../frontend/src/components/Step1GraphBuild.vue), [frontend/src/components/Step3Simulation.vue:638](../../frontend/src/components/Step3Simulation.vue), [frontend/src/components/Step4Report.vue:1842](../../frontend/src/components/Step4Report.vue), [frontend/src/views/Process.vue:506](../../frontend/src/views/Process.vue). | Thai must use a deliberate formatting policy (e.g. `th-TH` with agreed calendar/number behaviour), while English should remain deterministic. |
| Quote display in simulation | Simulation action rendering has a dedicated `original_content` / quoted block. [frontend/src/components/Step3Simulation.vue:170-181](../../frontend/src/components/Step3Simulation.vue), [frontend/src/components/Step3Simulation.vue:1159-1175](../../frontend/src/components/Step3Simulation.vue) | It preserves source/repost text but presently has no visible “Quoted source evidence” / “หลักฐานจากต้นฉบับ” label. |

### 2. Project and task API strings

| Surface | Evidence | Why it leaks |
| --- | --- | --- |
| Task title persisted/returned to clients | Graph construction creates its task with Chinese `构建图谱: ...`. [backend/app/api/graph.py:637-640](../../backend/app/api/graph.py) | This title is stored in the in-memory task and returned by `/task/<id>` unchanged. [backend/app/models/task.py:27-48](../../backend/app/models/task.py), [backend/app/api/graph.py:842-860](../../backend/app/api/graph.py) |
| Per-request and background task status | Many graph task messages already use `t(...)`, including completion and failure. [backend/app/api/graph.py:655-815](../../backend/app/api/graph.py) | This is the right seam, but errors caught from libraries are passed through raw (`str(e)` / traceback), so a provider’s Chinese message can still surface. [backend/app/api/graph.py:801-815](../../backend/app/api/graph.py) |
| Project lifecycle | Project data contains requirement, ontology, and graph metadata but no locale. [backend/app/models/project.py:27-106](../../backend/app/models/project.py) | A graph build retried from a later browser request can switch language because it only uses request locale. |

### 3. Simulation creation, configuration, profiles, and logs

| Surface | Evidence | Why it leaks |
| --- | --- | --- |
| Configuration prompts and fallback content | The configuration generator contains Chinese system prompts, JSON examples, fallback reasoning, context headings and default “Chinese routine” assumptions. [backend/app/services/simulation_config_generator.py:590-610](../../backend/app/services/simulation_config_generator.py), [backend/app/services/simulation_config_generator.py:654-718](../../backend/app/services/simulation_config_generator.py), [backend/app/services/simulation_config_generator.py:871-911](../../backend/app/services/simulation_config_generator.py) | `get_language_instruction()` is appended after a Chinese base prompt, but fallback values are Chinese and there is no output-language validation/retry. Generated `reasoning`, posts and topics are later shown in configuration/simulation views. |
| Persona prompts and fallback/profile display | Persona system prompt, JSON field descriptions, retrieval context, rule fallbacks and emitted profile console content are Chinese. [backend/app/services/oasis_profile_generator.py:447-538](../../backend/app/services/oasis_profile_generator.py), [backend/app/services/oasis_profile_generator.py:727-824](../../backend/app/services/oasis_profile_generator.py), [backend/app/services/oasis_profile_generator.py:1007-1092](../../backend/app/services/oasis_profile_generator.py) | Appending the language instruction does not translate the generated/fallback data. Profile fields feed personas and simulated speech. |
| OASIS simulation process log | The runner scripts print Chinese lifecycle, error, IPC and progress messages; parallel runner is the normal multi-platform path. [backend/scripts/run_parallel_simulation.py:97-103](../../backend/scripts/run_parallel_simulation.py), [backend/scripts/run_parallel_simulation.py:327-413](../../backend/scripts/run_parallel_simulation.py), [backend/scripts/run_parallel_simulation.py:1127-1209](../../backend/scripts/run_parallel_simulation.py) | These strings are written to simulation output/logs. They need a locale carried in `simulation_config.json` (and consumed by subprocesses), not only Flask thread-local state. |
| Action log payloads | Action logger serializes action/round/start/end records for the live simulation viewer. [backend/scripts/action_logger.py:53-117](../../backend/scripts/action_logger.py) | Actions preserve generated post/comment content; UI labels must identify preserved original/quoted evidence separately from generated content. |
| Runner monitor | The server monitor restores a captured locale before reading/updating run state. [backend/app/services/simulation_runner.py:580-651](../../backend/app/services/simulation_runner.py) | It is currently capture-based rather than run-bound, so refresh/retry can change locale.

### 4. Graph-memory, report, chat, and exports

| Surface | Evidence | Why it leaks |
| --- | --- | --- |
| Graph-memory summaries | The memory updater captures/restores locale in a worker, but its content templates and summaries need auditing/translation at their source. [backend/app/services/zep_graph_memory_updater.py:300-306](../../backend/app/services/zep_graph_memory_updater.py), [backend/app/services/zep_graph_memory_updater.py:410-430](../../backend/app/services/zep_graph_memory_updater.py) | Memory text becomes graph facts/search context and can be repeated in reports and chat. |
| Tool/search/interview context | `zep_tools.py` builds search, entity, panorama and interview text with Chinese headings, defaults, prompts, summary text, and errors. [backend/app/services/zep_tools.py:51-128](../../backend/app/services/zep_tools.py), [backend/app/services/zep_tools.py:177-291](../../backend/app/services/zep_tools.py), [backend/app/services/zep_tools.py:1351-1469](../../backend/app/services/zep_tools.py), [backend/app/services/zep_tools.py:1638-1734](../../backend/app/services/zep_tools.py) | This context drives agent chat and report generation. The quote rule only has a `zh` versus English branch, not Thai. [backend/app/services/zep_tools.py:1696](../../backend/app/services/zep_tools.py) |
| Report outline, sections, fallback report and chat | Report prompts, defaults, tool schemas and fallback text are predominantly Chinese. [backend/app/services/report_agent.py:540-865](../../backend/app/services/report_agent.py), [backend/app/services/report_agent.py:1121-1256](../../backend/app/services/report_agent.py), [backend/app/services/report_agent.py:1312-1559](../../backend/app/services/report_agent.py), [backend/app/services/report_agent.py:1826-1849](../../backend/app/services/report_agent.py) | The language instruction is appended to key LLM prompts, but generated fields are not validated; fallbacks directly persist Chinese to markdown/JSON. |
| Report status and logs | Structured report events use `t(...)` and are a good localization seam. [backend/app/services/report_agent.py:101-302](../../backend/app/services/report_agent.py), [backend/app/services/report_agent.py:1637-1797](../../backend/app/services/report_agent.py) | Free-form exception messages and LLM/tool output still enter agent JSONL and console logs unchanged. |
| Report artifact/export | Report manager persists `full_report.md`, `outline.json`, `section_*.md`, `agent_log.jsonl`, and `console_log.txt`. [backend/app/services/report_agent.py:1938-2002](../../backend/app/services/report_agent.py) | Locale and evidence metadata must be stored alongside the report at creation so exports/reloads label quotations correctly without altering legacy artefacts. |

## Shared implementation seams

1. **Locale contract (highest leverage).** Make `en` and `th` an explicit allow-list shared by browser and backend; normalize legacy `zh` to `en` on browser boot and backend input. Delete/stop loading the Chinese catalog. Complete `th.json` before claiming Thai UI support.
2. **Persistence contract.** Add `project_locale` to `Project`, copy it to immutable `run_locale` on `SimulationState` and into simulation/report config/artifact metadata. All workers, subprocesses, retries and report/chat tasks read the persisted owner locale—not `Accept-Language` after creation.
3. **Translation and copy seam.** Use locale catalog keys for fixed UI/API/progress/log messages. `Process.vue` is an isolated legacy page that must be converted or retired; it cannot be repaired by filling JSON catalogs alone.
4. **Generated-text boundary.** Centralize a validator over natural-language output fields. It should reject Chinese in generated fields, retry once with the locale instruction, then persist a localized explicit failure. It must not validate/rewrite fields marked as quoted source evidence.
5. **Evidence boundary.** Represent source/quote excerpts with a `quoted_source_evidence` marker through action records, tool results, reports and exports. Render a translated label at every display/export boundary; preserve evidence text byte-for-byte.
6. **Prompt/fallback seam.** Convert base prompts, tool descriptions, rules, defaults and fallback strings in config generation, personas, Zep tools, and reports to locale-selected templates. Adding a language instruction alone cannot make deterministic fallback content Thai/English.

## Thai typography and formatting requirements

- Current shared/UI typography repeatedly specifies `JetBrains Mono`; the language selector itself does so. [frontend/src/components/LanguageSwitcher.vue:63-79](../../frontend/src/components/LanguageSwitcher.vue) This is inappropriate as the primary Thai body font and can make Thai hard to read.
- Establish a Thai-capable sans-serif text stack for `html[lang="th"]`, retain mono only for IDs/code, and test mixed Thai/Latin wrapping in long report titles, chips, action logs and Markdown rendering. Existing styling already contains `html[lang="en"]` overrides, offering the pattern for a Thai override. [frontend/src/components/Step4Report.vue:5158-5163](../../frontend/src/components/Step4Report.vue)
- Replace hard-coded `en-US`/`zh-CN` date formatters with a locale-to-BCP-47 formatter and make the Thai calendar choice explicit (Gregorian vs Buddhist Era). This is a product decision, not a safe implicit change.

## Decisions needed before implementation

1. Confirm whether the legacy `Process.vue` route remains supported. If it does, it is a required full i18n migration; if not, redirect/remove it so no Chinese UI remains reachable.
2. Choose Thai date convention: Thai locale with Buddhist Era (native expectation) or Thai language with Gregorian years (cross-run comparability).
3. Define a machine-readable evidence schema and the complete field allow-list for language validation. Applying character detection to raw documents, names, IDs, source quotes, or historical artefacts would corrupt the agreed preservation rule.
4. Decide whether external provider error text is shown verbatim in a developer-only diagnostic view or replaced with a localized user-safe error plus a correlation ID. It cannot meet the “all user-visible generated text” requirement if raw provider errors are surfaced.

## Suggested verification matrix

- Fresh English project → graph build → simulation → report/chat/export: no Chinese code points in generated fields, UI, task messages, or logs.
- Fresh Thai project: all UI and generated text Thai; Thai text has readable font/wrapping; date rule matches the chosen policy.
- Change interface language after creating project/run: project/run artefacts retain their captured locale; UI chrome changes only.
- Refresh/retry/background/report tasks: persisted locale remains unchanged.
- Chinese uploaded document and Chinese source quote: original text remains intact and each rendered/exported excerpt carries the localized evidence label.
- Legacy pre-change run/report: content is unchanged and no automatic translation occurs.
