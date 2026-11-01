# MiroFish Zep dependency surface and portable data contract

## Scope and method

This is a code-level investigation for the decision ticket **Research: MiroFish
Zep dependency surface and portable data contract**. It describes the currently
pinned `zep-cloud==3.25.0` integration, not a migration implementation or a
recommendation for a particular replacement. Local source is the primary
evidence for the application's actual requirements.

## Finding: Zep is a graph-memory implementation, but its identifier crosses application boundaries

`Project.graph_id` is persisted and copied into each `SimulationState`; report
generation then reads that same id. This makes the current `graph_id` both a
provider identifier and an application identifier. A replacement must separate
those concepts before it can coexist with Zep or support a clean cutover.

Evidence:

- [project model](../../backend/app/models/project.py#L35-L105) persists
  `graph_id`, Zep batch identity, upload files and ontology.
- [simulation state](../../backend/app/services/simulation_manager.py#L35-L125)
  persists `graph_id` and immutable run locale.
- [report API](../../backend/app/api/report.py#L125-L185) verifies that the
  project and simulation graph identifiers agree before creating a report.

## Exact Zep Cloud operations in use

| MiroFish phase | Current calls | Behaviour MiroFish relies on |
| --- | --- | --- |
| Graph creation | `graph.create`, `graph.get`, `graph.delete` | Caller-generated graph id; lost create replies are reconciled by read; deletion is lifecycle-guarded. |
| Schema | `graph.set_ontology` with dynamically built entity/edge models | Optional typed entities, attributes, and allowed source/target edge types shape extraction. |
| Source-document ingestion | `batch.create`, `batch.add(BatchAddItem)`, `batch.process`, `batch.get`, `batch.list`, `batch.list_items` | Asynchronous, durable batch identity; each upload chunk is a text graph episode with SHA-256 and source metadata. |
| Processing barrier | `graph.episode.get` | A report/simulation preparation cannot assume an accepted episode is searchable until `processed` is true. |
| Simulation-memory ingestion | `graph.add` | Append a timestamped text episode plus simulation/platform/round/action metadata; no automatic retry after an ambiguous write. |
| Derived graph reads | paged `graph.node.with_raw_response.get_by_graph_id`, `graph.edge.with_raw_response.get_by_graph_id`, `graph.node.get`, `graph.node.get_edges` | Enumerate node/edge graph; MiroFish works around a one-direction `get_edges` behaviour by filtering all edges for complete context. |
| Retrieval | `graph.search(graph_id, query, limit, scope, reranker="cross_encoder")` | Semantic/hybrid search over edges or nodes. The report calls it repeatedly for subquestions and relies on returned facts, nodes and edges. |

Primary source references: [shared client and limits](../../backend/app/utils/zep.py),
[pagination](../../backend/app/utils/zep_paging.py),
[graph build](../../backend/app/services/graph_builder.py#L218-L879),
[simulation ingestion](../../backend/app/services/zep_graph_memory_updater.py#L442-L639),
and [retrieval](../../backend/app/services/zep_tools.py#L462-L945).

## Data currently read or written

### Source document episode

The graph builder writes the upload chunk itself in `data`; it also writes
`source_description`, `mirofish_operation_id`, `chunk_index`, and
`chunk_sha256`. The batch returns a server episode UUID for every accepted
chunk. The chunk is the only data that is explicitly an original source
artifact, and must remain byte-for-byte/verbatim in any portable store.

Source: [batch item construction](../../backend/app/services/graph_builder.py#L415-L564).

### Simulation episode

An `AgentActivity` contains platform, agent id/name, action type, original
action arguments, round, and timestamp. The updater currently renders it to a
locale-dependent natural-language line and batches several lines into an
episode. Its episode metadata is:

```text
source=mirofish_simulation
simulation_id, platform, activity_count, first_round, last_round,
agent_ids, action_types
```

The stored natural-language wrapper is a lossy representation: individual
action arguments and their provenance are not separately persisted in Zep
metadata. Therefore a migration cannot reconstruct reliable quoted evidence
from existing simulation episodes alone.

Source: [activity model/rendering](../../backend/app/services/zep_graph_memory_updater.py#L20-L204)
and [episode metadata](../../backend/app/services/zep_graph_memory_updater.py#L488-L525).

### Derived graph records

MiroFish reads:

- node: provider UUID, name, labels, summary, attributes, created-at;
- edge: provider UUID, relation name, fact, source/target node UUIDs,
  attributes, created/valid/invalid/expired timestamps, and linked episode ids;
- search: edge facts plus node summaries; and
- ontology: entity type descriptions/attributes and edge type descriptions,
  attributes and source-target constraints.

The exact graph API response is normalized into DTOs by
[ZepEntityReader](../../backend/app/services/zep_entity_reader.py#L20-L453),
[GraphBuilderService.get_graph_data](../../backend/app/services/graph_builder.py#L810-L873),
and [ZepToolsService](../../backend/app/services/zep_tools.py#L462-L945).

## Consumers and what they actually need

| Consumer | Minimum needed from the memory backend | Important distinction |
| --- | --- | --- |
| Project build/UI | create graph, set optional ontology, ingest original chunks, wait for indexing, list graph data, delete | UI displays node/edge timestamps and episode linkage. |
| Simulation preparation | enumerate typed entities with summaries, attributes and all incoming/outgoing relations | Only nodes with labels beyond `Entity`/`Node` are candidates for personas. |
| Persona enrichment | semantic edge search and semantic node search for one entity | This is contextual enrichment, not primary evidence. |
| Simulation runner | append action events, wait until they are indexed before declaring graph ingestion complete | It must fail loudly on uncertain writes, not replay a non-idempotent append. |
| Report agent | semantic search, node/edge lookup/enumeration, temporal edge state, and an independent interview operation | `interview_agents` calls OASIS and reads profile files; it is **not** a Zep capability. |
| Report/chat evidence | retrieval result plus immutable references to original text | Current text-only tool output cannot prove whether a graph fact is original source, simulation output, or derived extraction. |

Primary source references: [profile enrichment](../../backend/app/services/oasis_profile_generator.py#L369-L485),
[simulation graph updater lifecycle](../../backend/app/services/simulation_runner.py#L408-L528),
and [report tool dispatch](../../backend/app/services/report_agent.py#L1035-L1177).

## Smallest portable contract

The narrowest safe seam is **two stores behind one Graph Memory Backend**:

1. an immutable evidence ledger owned by MiroFish, and
2. a replaceable derived graph/retrieval index.

Do not make a graph database the sole evidence store. An extraction engine may
change node summaries/facts, ranking, or graph identifiers without altering
the original evidence.

```python
class GraphMemoryBackend(Protocol):
    # Application identity, never a provider UUID
    def create_space(self, *, space_id: str, name: str) -> None: ...
    def delete_space(self, *, space_id: str) -> None: ...
    def set_ontology(self, *, space_id: str, ontology: Ontology) -> None: ...

    # Immutable evidence first. payload is preserved verbatim; sha256 is verified.
    def append_evidence(self, records: Sequence[EvidenceRecord]) -> AppendReceipt: ...
    def wait_until_indexed(self, receipt: AppendReceipt, *, deadline: datetime) -> None: ...
    def get_evidence(self, evidence_id: str) -> EvidenceRecord: ...

    # Derived, replaceable graph and retrieval view.
    def search(self, *, space_id: str, query: str, scope: Literal["edges", "nodes"],
               limit: int) -> SearchPage: ...
    def list_nodes(self, *, space_id: str, cursor: str | None = None) -> Page[Node]: ...
    def list_edges(self, *, space_id: str, cursor: str | None = None) -> Page[Edge]: ...
    def get_node(self, node_id: str) -> Node | None: ...
    def list_incident_edges(self, *, space_id: str, node_id: str) -> Page[Edge]: ...
```

`EvidenceRecord` must include at least:

```text
evidence_id (MiroFish UUID), space_id, kind (source_document | simulation_event |
interview_response), payload_verbatim, sha256, occurred_at, ingested_at,
locale_at_creation, provenance (project/run/file/chunk or simulation/platform/
round/agent/action), and immutable=true.
```

`Node`, `Edge`, and `SearchHit` must carry `evidence_refs: list[evidence_id]`
and a `derivation` value (`extracted`, `summary`, `retrieval_context`). A report
may render **Quoted source evidence** only after resolving an evidence ref and
using `payload_verbatim`; unreferenced graph facts are labelled derived graph
evidence. This preserves the current product rule that language validation
does not translate quoted source material.

The contract needs typed error categories: `not_found`, `invalid_input`,
`unavailable`, `write_outcome_unknown`, and `indexing_failed`. In particular,
the adapter must not silently turn unavailable retrieval into an empty result,
or replay an append whose outcome is unknown.

## Compatibility phases implied by the evidence

1. **Introduce application-owned `memory_space_id` and the evidence ledger.**
   Keep `zep_graph_id` as an adapter implementation detail, not the project
   identity. New evidence writes can be dual-written only when their receipt is
   durable and idempotency is explicit.
2. **Adapt the current Zep implementation.** Map source chunks and simulation
   actions to `EvidenceRecord` before rendering text; map Zep episodes/edges
   back to derived records with their evidence refs where possible.
3. **Run parity tests on new projects/runs.** Compare typed entities, complete
   incident edges, temporal states, search hit evidence refs, and report quote
   resolution. Ranking equality is not required; evidence reachability is.
4. **Cut over new projects only.** Existing Zep graphs remain legacy/read-only.
   Their graph facts cannot honestly gain source provenance after the fact,
   so reports should label them derived unless the original upload/action file
   provides a deterministic match.

## Decisions this research enables

- A future open-source option needs a graph projection plus vector/keyword
  retrieval and temporal edge fields; a vector database alone cannot preserve
  the current graph UI/persona-selection behaviour.
- The first migration decision is whether the evidence ledger is a local
  append-only file/database in the MiroFish volume. That decision is
  independent of choosing a graph/vector engine.
- OASIS interviews/surveys should remain behind a separate simulation-runtime
  interface. Replacing Zep alone must not change the requirement that the
  simulation environment remains available for interview actions.
