# Scientific RAG implementation status

- Phase A started from a working tree containing the untracked audit directory. Existing storage, prompt experiments, specialists, transports and tests were reviewed.
- Phases B–D added exact document filtering, reciprocal rank fusion and a corpus QA path with bounded follow-up and separate provenance and semantic checks.
- Engineering reference: [The New SDLC With Vibe Coding](https://reu.techconf.org/document/06-Reading-materials/The-New-SDLC.pdf). The QA path uses bounded execution, explicit structured contracts and inspectable retrieval and validation traces.
- Phase E added shared corpus search and QA to Streamlit and the MCP SDK adapter. The SDK test verifies root-relative ingestion, duplicate identity, document-scoped search, evidence lookup and abstention.
- Phase F completed the local ranking pilot and the 163-test Windows suite. The generation pilot exposed false semantic acceptances and motivated a numeric consistency check.
- Phase G exercised three pinned PDFs through SDK stdio and a server restart. All 12 retrieved excerpts matched their PDF pages. The final live QA run returned no factual claims. See the [implementation report](docs/FINAL_IMPLEMENTATION_REPORT.md) for demonstrations and remaining acceptance gaps.
