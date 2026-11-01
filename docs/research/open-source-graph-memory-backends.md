# Open-source graph-memory backends for a future MiroFish migration

## Decision this research informs

Assess a future replacement for Zep Cloud that runs on one private Docker host,
keeps new runs self-hosted, and supports the MiroFish paths that matter: source
and simulation episode ingestion, semantic retrieval, entity/relation graph,
time-aware facts, and evidence returned to report/chat. This is research only:
it makes no product or deployment change.

## Current boundary and parity target

MiroFish currently couples its graph lifecycle to Zep Cloud in the graph
builder, entity reader, simulation updater, and report tools. It sends uploaded
source chunks and incremental simulation actions as episodes; later it reads
nodes, edges/facts, search results and graph statistics. The source and action
artifacts in MiroFish's own upload directories are the portable ground truth;
derived Zep graph data is not an adequate sole migration source.

Zep is more than a graph database. Its model is temporal: episodes provide
provenance, facts/relations carry validity periods, and retrieval combines
semantic, full-text, and graph search. Its managed service also supplies
context assembly and operational tooling. [Zep concepts](https://help.getzep.com/concepts)
and [Zep search](https://help.getzep.com/searching-the-graph) document those
behaviours. Any self-hosted replacement must either retain them through a
framework or deliberately reimplement them in MiroFish.

The required parity criteria are therefore:

1. Append a source or action as an immutable episode, including provenance and
   timestamp.
2. Extract/deduplicate typed entities and relationships incrementally.
3. Preserve both `valid_at`/`invalid_at`-style history and the ingest time;
   never overwrite old facts silently.
4. Retrieve ranked graph evidence by semantic, lexical, and relation context,
   returning structured provenance rather than pre-rendered prose.
5. Run with persistent Docker volumes on one host. The database can be local
   while model inference remains a separately chosen local or remote provider.

## Candidates

| Candidate | What it supplies | Fit to parity | License / single-host posture | Conclusion |
| --- | --- | --- | --- | --- |
| **Graphiti + FalkorDB** | Graphiti is an OSS temporal context-graph framework with episode provenance, typed entities/edges, validity windows, incremental ingestion and hybrid retrieval. It supports FalkorDB as a graph driver and documents Docker Compose / a one-container FalkorDB quick start. | **Closest direct replacement.** It covers the application-level temporal-memory semantics that a raw graph DB does not. MiroFish still owns its API adapter, jobs, evidence DTOs, retries, and UI. | Graphiti is Apache-2.0. FalkorDB is SSPLv1: source-available but not OSI open source; evaluate that separately if redistribution/SaaS obligations matter. | **Recommended first prototype** for functional parity on a private personal host. |
| **Graphiti + Neo4j Community** | Same Graphiti layer, backed by a mature property graph with Cypher and vector indexes. | Near-equivalent technical architecture. Graphiti supplies temporal invalidation/provenance; Neo4j stores it. | Neo4j Community is GPLv3 and is intended for a single instance; it has official Docker deployment. | **Viable alternative** if its operational maturity is preferred and GPLv3 is acceptable. |
| **Cognee** | An OSS memory platform that builds a self-hosted graph from data and combines vector retrieval, graph reasoning and ontology generation. It has Docker Compose and graph/vector database adapters. | Good discovery candidate, but it is a different ingestion/retrieval product rather than a small Zep-compatible storage layer. Its public material does not establish Zep-equivalent bi-temporal fact invalidation or episode-to-fact provenance for this use case. | Apache-2.0; Docker-supported. | **Prototype only after Graphiti**; larger semantic/API migration risk. |
| **Mem0 OSS graph memory** | Extracts entities/relations on writes, keeps vectors and graph links, and provides self-hosted server Docker deployment. | Useful for long-term agent memory; less proven for MiroFish's report-grade episode provenance and explicit validity lifecycle. Validate its graph mode and evidence export before selecting. | Apache-2.0; self-hosted server available. | **Not first choice** for simulation graph/report parity. |
| **FalkorDB alone / Neo4j Community alone** | Native property graph, Cypher-style queries, vector indexes; both can run on a local Docker host. | Storage foundation only. MiroFish would need to build extraction, entity resolution, temporal invalidation, hybrid ranking, episode tracking and context assembly itself. | FalkorDB SSPLv1; Neo4j Community GPLv3. | **Do not use alone** for the first migration. Use underneath Graphiti if selected. |
| **Qdrant or Weaviate** | Strong vector similarity, metadata filters and lexical/hybrid retrieval; local Docker deployment. | No native general entity/relation graph or temporal fact lifecycle. A separate graph plus application orchestration is required. | Qdrant Apache-2.0; Weaviate BSD-3-Clause. | **Supporting retrieval store, not a Zep replacement.** |
| **Apache AGE + pgvector** | PostgreSQL graph extension with openCypher-in-SQL and ACID storage; can be paired with pgvector. | Permissive DIY foundation, but all temporal-memory extraction, invalidation and hybrid retrieval must be designed by MiroFish. | Apache-2.0. | **Only if permissive licensing outweighs build cost.** |

## Evidence behind the shortlist

### Graphiti is the highest-parity candidate

Graphiti is the open-source temporal context-graph engine that originated at
Zep. Its upstream repository describes entities, relationships/facts with
validity windows, raw episodes as provenance, learned or prescribed ontology,
incremental updates, and hybrid semantic/keyword/graph retrieval. It can run
on Neo4j or FalkorDB, has an optional REST service, and supports
OpenAI-compatible local inference endpoints such as Ollama/vLLM/llama.cpp/LM
Studio. See the [Graphiti README](https://github.com/getzep/graphiti) and the
[Graphiti product documentation](https://www.getzep.com/platform/graphiti/).

This matters because the semantic model is already close to the MiroFish
episode/fact/report flow. It is not a Zep Cloud API clone: Zep states that
Graphiti needs the application to build its own user/conversation management,
tooling, performance operations and surrounding service layer. The migration
should therefore be an adapter project, not a host/URL configuration change.

### Raw stores do not replace the temporal-memory layer

FalkorDB provides a property graph, OpenCypher, full-text and vector indexes,
plus a documented persistent Docker volume; its repository is licensed SSPLv1.
([docs](https://docs.falkordb.com/), [source/license](https://github.com/FalkorDB/FalkorDB))
Neo4j Community has official single-instance Docker instructions, Cypher and
vector indexes, but its repository license is GPLv3.
([operations manual](https://neo4j.com/docs/operations-manual/current/docker/introduction/),
[vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/),
[license](https://github.com/neo4j/neo4j))

Both can store timestamps, but neither source documents automatic fact
invalidation, episode provenance, entity extraction, or report-context
assembly. Those are Graphiti/MiroFish responsibilities.

Qdrant is an Apache-2.0 vector DB with JSON payload filtering and an official
persistent Docker quick start, but no entity/relation graph traversal.
([quick start](https://qdrant.tech/documentation/quick-start/),
[payload/filter model](https://qdrant.tech/documentation/concepts/payload/),
[license](https://github.com/qdrant/qdrant/blob/master/LICENSE))
Weaviate similarly provides vectors, BM25/filtering and directional object
references, but not a general graph engine or temporal fact semantics.
([data model](https://weaviate.io/developers/weaviate/concepts/data),
[Docker deployment](https://weaviate.io/developers/weaviate/installation/docker-compose),
[license](https://github.com/weaviate/weaviate/blob/main/LICENSE))

Apache AGE is an Apache-2.0 PostgreSQL graph extension with openCypher embedded
in SQL and an official Docker image; adding semantic search would require
pgvector or another vector store. ([overview](https://age.apache.org/overview/),
[quick start](https://age.apache.org/getstarted/quickstart/))

### Other memory products are viable experiments, not a parity assertion

Cognee documents an OSS self-hosted knowledge-graph pipeline with vector and
graph retrieval, adapters, and Docker Compose. Its own quick start exposes
`remember`, `recall`, `forget` and `improve` rather than the episode/fact API
MiroFish currently uses. ([Cognee source](https://github.com/topoteretes/cognee))

Mem0 documents a self-hosted Docker server, Apache-2.0 licensing, and graph
memory that extracts entities/relations while storing vectors. It is credible
for a separate agent-memory feature, but its public graph-memory description
does not by itself prove the required bi-temporal fact lifecycle and
report-evidence provenance. ([Mem0 source](https://github.com/mem0ai/mem0),
[graph-memory docs](https://docs.mem0.ai/open-source/features/graph-memory))

## Recommended future route (not approved implementation)

1. **Keep Zep for all existing projects/runs.** Treat its artifacts as legacy;
   do not attempt to translate or mutate old reports or derived graph records.
2. **Define a narrow `GraphMemoryBackend` port before selecting storage.** It
   should operate in terms of MiroFish-owned `Episode`, `Fact`, `Entity`,
   `Relation`, `EvidenceRef`, and `GraphQuery` types—not Zep SDK DTOs or a
   rendered string. The return types must retain evidence kind, source artifact
   reference, event time, ingest time and validity range.
3. **Build a disposable Graphiti + FalkorDB proof of concept against a copied,
   non-production fixture.** It should ingest one upload and a few action-log
   entries, then prove: a) source is retained verbatim; b) changed facts retain
   history; c) semantic and relation retrieval work; d) the report tool sees
   structured evidence; e) all data survives a container restart.
4. **Mirror writes for new test runs only.** Compare results with Zep using
   recorded fixtures and failure injection. Do not dual-read user reports until
   parity criteria have explicit tests and an operator-visible mismatch state.
5. **Cut over only new projects/runs after acceptance.** Persist immutable
   `memory_backend` and backend graph identity in project/run state. Existing
   Zep runs remain read-only legacy artifacts; re-ingest from MiroFish's raw
   source/action files only when a user explicitly requests a new run.

## Open decisions before any implementation

- Is SSPLv1 acceptable for a private single-host installation? If not, the
  Graphiti proof should use Neo4j Community (GPLv3) or the scope expands to a
  permissively licensed DIY storage design.
- Is an external LLM/embedding endpoint acceptable while data storage is local,
  or must inference also be local? Graphiti supports OpenAI-compatible local
  endpoints, but structured extraction quality must be measured with Thai and
  English fixtures.
- What evidence schema and export format will be the stable public contract?
  This must be settled before an adapter so source evidence remains verbatim
  while generated EN/TH explanations stay locale-controlled.
- What success threshold will justify changing a personal production workflow:
  test corpus, retrieval quality, ingestion duration, recovery after restart,
  and disk/RAM limits?

## Bottom line

For the stated private, Docker-first and migration-safe goal, evaluate
**Graphiti + FalkorDB first**. It preserves the hard parts that distinguish Zep
from a vector database—episodes, provenance, temporal validity, incremental
graph construction and hybrid graph retrieval—while moving data storage and
orchestration under local control. Choose **Graphiti + Neo4j Community** if
FalkorDB's SSPLv1 is unacceptable. Do not select a raw vector store or raw
graph database as a drop-in replacement: that would turn a migration into a
new memory-engine project.
