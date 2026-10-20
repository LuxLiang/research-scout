# Research RAG

Scout retrieves potential uses of new techniques and reopens source/target proof
context before publishing transfer reports. Retrieval is not proof verification.

## GitHub projects inspected

Reviewed on 2026-10-20. Original local implementations borrow these patterns;
no upstream source is vendored and no framework service is installed.

| Project | Source inspected | Decision |
| --- | --- | --- |
| [LlamaIndex](https://github.com/run-llama/llama_index), MIT | [QueryFusionRetriever](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/retrievers/fusion_retriever.py), [RecursiveRetriever](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/retrievers/recursive_retriever.py) | Adopt independent rank fusion and small-to-big source retrieval |
| [Haystack](https://github.com/deepset-ai/haystack), Apache-2.0 | [DocumentJoiner](https://github.com/deepset-ai/haystack/blob/main/haystack/components/joiners/document_joiner.py) | Adopt weighted reciprocal-rank fusion and modular retrieval/reranking boundaries |
| [RAGFlow](https://github.com/infiniflow/ragflow), Apache-2.0 | Repository architecture/document-processing overview | Considered as an integrated service; retain Scout's existing local archive and scientific contracts |

## Retrieval and evidence

`retrieval/fusion.py` combines BM25 over scientific fields, explicit mathematical
structure overlap and bounded one-hop reference expansion. Reciprocal-rank fusion
deduplicates votes within each channel. Scores order reading candidates, not
scientific confidence. Optional semantic/reranker callables validate returned IDs
and fail explicitly. No embedding model or neural reranker is enabled by default.

`retrieval/sources.py` builds a disposable FTS5 index under
`<cache>/retrieval/sources.sqlite3`. Child windows of about 1,200 characters refer
to containing parent windows of about 4,800 characters, preserving Unicode offsets
and nearby word boundaries. These positions address the text cache, not PDF pages.
Passages carry paper/version IDs, source/text hashes, coverage and currentness.
Missing sources and hash mismatches remain in the manifest. `UNVERIFIABLE` means
the original-file hash could not be checked even if cached text is available.

Source edits/deletions change the review fingerprint. Cached passage lookup
rejects changed artifacts. Default search uses current versions; an unavailable
current source never silently substitutes an older version. Explicit version
filters allow historical reading, and candidate rereading pins the versions used
by its source result and target evidence.

`retrieval/context.py` preserves the entire extracted scientific inventory and
the existing full-evidence/windowed-reading protocol. Ranked source windows are
supplementary, explicitly budgeted and partial. Each focused technique gets
traceable queries; after generation each candidate's proposed bridge retrieves
source and target context separately. Model grounding receives original canonical
evidence plus source windows and may narrow or remove a candidate.

Reports retain queries, channel ranks/reasons, source availability and exact
version/hash/span provenance. A retrieval miss is unknown, not a negative
literature finding. `source_passage_ids` are reading references, not canonical
Evidence IDs; newly relevant passages need a separate attributed extraction
before supporting stronger formal records. Retrieval cannot promote science.

## Inspect and evaluate

```bash
scout --workspace /path/to/library index sources
scout --workspace /path/to/library index retrieve 'conditional Gaussian smoothing'
scout --workspace /path/to/library index retrieve 'local entropy' --paper-id PAPER_ID
scout --workspace /path/to/library index retrieve 'local entropy' --version-id VERSION_ID
scout index eval
```

No model or network is needed. Source filters apply before source ranking/limits;
record hits are labeled separately. `index eval` measures hit rate, MRR and recall
on labeled **SYNTHETIC** regressions, including cross-field structure retrieval and
an explicit semantic-alias stub. These scores test software behavior, not real
research-discovery performance. A curated real-paper benchmark and configured
embedding/reranker remain future evaluation work.
