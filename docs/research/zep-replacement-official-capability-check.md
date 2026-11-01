# Official capability check: replacing Zep Cloud for MiroFish

## Scope

This note checks the existing Zep dependency surface against first-party,
current documentation. It supplements, rather than replaces,
[the portable contract](zep-dependency-surface-and-portable-contract.md) and
[the broader candidate review](open-source-graph-memory-backends.md). It makes
no application or infrastructure change.

The actual MiroFish boundary is verified locally: source chunks and simulation
activity are submitted as textual episodes; the application later needs typed
nodes and edges, temporal facts, cursor-safe enumeration, and separate node and
edge semantic search. See [graph builder](../../backend/app/services/graph_builder.py),
[activity updater](../../backend/app/services/zep_graph_memory_updater.py), and
[report retrieval](../../backend/app/services/zep_tools.py).

## Conclusion

**Graphiti plus a self-hosted graph database is the only candidate checked here
that directly documents all of MiroFish's semantic requirements:** raw episode
provenance, typed ontology, incremental extraction, temporal fact history and
hybrid graph retrieval. It is a *migration*, not a Zep endpoint replacement:
MiroFish must retain its own evidence ledger, jobs/status API, pagination DTOs,
retry rules and UI.

For a first proof of concept, use **Graphiti + Neo4j Community** when a mature
Python/Cypher operational surface is preferred. Use **Graphiti + FalkorDB** only
after accepting its licence and validating its operations on the target host.
Neither raw Neo4j nor raw FalkorDB supplies the Zep/Graphiti extraction and
temporal-memory layer on its own.

## Capability matrix

| MiroFish requirement | Graphiti | Neo4j alone | FalkorDB alone | Decision impact |
| --- | --- | --- | --- | --- |
| Developer-defined entity/edge types | Documents prescribed Pydantic ontology alongside learned ontology. | Labels, relationship types and properties can model it, but extraction is application work. | Same storage-level modelling position. | Graphiti meets this closest to the current dynamic ontology call. |
| Source/action ingestion and extraction | Adds text or structured JSON episodes and incrementally extracts graph records. | Stores data only; MiroFish must perform chunking, LLM extraction and entity resolution. | Stores data only; MiroFish must perform those steps. | Keep MiroFish file/text extraction before the backend in all cases. |
| Evidence provenance | Every fact traces to a raw episode. | Possible only if MiroFish models immutable evidence explicitly. | Possible only if MiroFish models immutable evidence explicitly. | Do not make any derived graph the evidence system of record. |
| Temporal changes | Validity windows and invalidation preserve prior facts. | Timestamp fields and version relationships are DIY. | Timestamp fields and version relationships are DIY. | Graphiti is substantially closer to current `valid_at` / `invalid_at` output. |
| Semantic + lexical + relation retrieval | Documents hybrid semantic, BM25 and graph traversal; provides edge and node searches. | Documents node and relationship vector indexes; lexical/hybrid policy is application-designed. | Its indexes/query language are a storage facility, not the extraction/retrieval policy. | A raw DB is not a drop-in replacement. |
| Python integration | Python-native `graphiti-core`; optional FastAPI server. | Official Python driver and Cypher. | Python client exists, but Graphiti owns the higher semantic layer. | MiroFish's Python backend can implement a dedicated adapter. |
| Self-hosting | Explicitly self-hosted; supports Neo4j/FalkorDB and Compose examples. | Official Docker deployment. | Docker quick-start documented by Graphiti. | Removes the Zep network hop, but database and inference health become local responsibilities. |

### Primary evidence

- The [Graphiti upstream README](https://github.com/getzep/graphiti) describes
  episodes as raw provenance, entities/relations with validity windows,
  prescribed Pydantic types, incremental construction, and hybrid semantic +
  keyword + graph retrieval. It also explicitly contrasts Graphiti's
  self-managed model with Zep's managed tools and services.
- Its [quick-start section](https://github.com/getzep/graphiti#quick-start)
  documents adding text/JSON episodes, hybrid edge search, graph-distance
  reranking and node search; the same README documents Neo4j and FalkorDB
  drivers plus Docker Compose profiles.
- The [Graphiti local-LLM guidance](https://github.com/getzep/graphiti#using-graphiti-with-openai-compatible-providers-and-local-llms)
  supports OpenAI-compatible local endpoints, but warns that extraction depends
  on reliable structured JSON output. This is an important Thai-fixture test,
  not an assumption of parity.
- [Neo4j's official Python manual](https://neo4j.com/docs/python-manual/current/)
  documents the supported Python driver and transactional Cypher interface.
  [Neo4j vector-index documentation](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
  confirms vector search for nodes and relationships, and says index creation
  is asynchronous; an adapter must expose readiness rather than treating a
  newly accepted write as searchable.
- The official [Neo4j GraphRAG Python knowledge-graph builder](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html)
  is a credible alternative *rebuild* path: it documents PDF/chunk ingestion,
  embedding, manual or LLM-derived schema, graph writing and entity resolution.
  Its [retrieval guide](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html)
  documents vector and hybrid-Cypher retrievers. It does not document
  Graphiti-style episode provenance or automatic temporal invalidation, so it
  needs the application-owned evidence and temporal models proposed above.
- FalkorDB's [official index documentation](https://docs.falkordb.com/cypher/indexing/)
  and [vector-index guide](https://docs.falkordb.com/cypher/indexing/vector-index/)
  document full-text and vector indexes, including relationships. They do not
  turn unstructured text into a temporal evidence graph; Graphiti or MiroFish
  must still do that work.

## Operational implications for the current "processing" symptom

Replacing the remote Zep API can eliminate one external connection dependency,
but cannot guarantee that graph construction becomes fast. Graphiti's own
documentation says ingestion performs concurrent LLM work and defaults
`SEMAPHORE_LIMIT` to 10 to avoid provider rate limiting. Therefore a local
database paired with a remote LLM can still wait on the model provider;
fully-local operation also needs an adequately capable local model and a
structured-output reliability test. Treat graph build as an explicit job with
per-episode state and a deadline, exactly as the portable contract requires.

## Safe phased proof of concept

1. Define the application-owned `EvidenceRecord` / `GraphMemoryBackend` seam
   described in the portable-contract note. Preserve source bytes, SHA-256,
   source/run/action provenance and ingestion status before calling either
   backend.
2. On a copied fixture only, run Graphiti + Neo4j in Docker. Feed the same
   already-extracted text chunks and a small simulation-action sequence; do
   not alter existing Zep projects.
3. Verify explicitly: episode can be resolved from each derived fact; ontology
   types are retained; changed facts keep a history; node and edge queries
   return evidence references; restart preserves all data; an unavailable
   database/LLM reports a visible failed or retryable job rather than an empty
   graph.
4. Only then test Graphiti + FalkorDB if its licensing and observed operations
   are acceptable. Dual-write new test runs only after writes have durable,
   idempotent receipts. Do not promise identical retrieval ranks: require
   evidence reachability and typed graph parity instead.

## Non-recommendations

- **Qdrant/Weaviate alone:** useful vector-retrieval components, but they do
  not replace the entity/relation, temporal-fact and graph-UI contract.
- **Neo4j/FalkorDB alone:** viable foundations only if the project elects to
  implement an extraction, provenance, invalidation and hybrid-ranking engine;
  that is materially more work than a backend substitution.
- **Memgraph alone:** it documents [vector search with traversal](https://memgraph.com/vector-search)
  and a [Python graph interface](https://memgraph.com/memgraph-for-python-developers),
  but no first-party evidence found for document-to-ontology extraction,
  episode-to-fact provenance or automatic temporal invalidation. Treat it as a
  graph/vector storage candidate, not a direct Zep replacement.
- **Kuzu through Graphiti:** Graphiti's upstream README marks that driver
  deprecated and directs new projects to Neo4j or FalkorDB.
