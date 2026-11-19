"""Optional corpus workspace, leaving the original single-paper interface intact."""
import asyncio
import hashlib
import json
import sqlite3
import streamlit as st
from research_swarm.config import ROOT
from research_swarm.service import ResearchService
from .config import CorpusConfig
from .ingest import CorpusPipeline
from .retrieval import EvidenceRetrieval, evidence_reference


def render_corpus():
    with st.expander("Research corpus — persistent evidence library"):
        if not st.checkbox("Enable corpus workspace",key="corpus_enabled"):
            return
        try:
            config = CorpusConfig.from_env()
            pipeline = CorpusPipeline(config)
            retrieval = EvidenceRetrieval(pipeline.store,config)
            service = ResearchService(config.pdf_dir, ROOT / "output" / "mcp", corpus_config=config)
            if st.session_state.get("corpus_database") != str(config.database.resolve()):
                st.session_state.pop("corpus_results",None)
                st.session_state.pop("corpus_answer",None)
                st.session_state["corpus_database"] = str(config.database.resolve())
            st.caption("Local metadata and page evidence. Import only PDFs you are entitled to store. "
                       "Discovery, automatic downloads and comparative reports are planned phases.")
            title = st.text_input("Publication title",key="corpus_title")
            doi = st.text_input("DOI (optional; never inferred)",key="corpus_doi")
            uploaded = st.file_uploader("Import a local PDF to deCitit/",type=["pdf"],key="corpus_pdf")
            if st.button("Register PDF",disabled=uploaded is None or not title.strip(),key="corpus_register"):
                publication = pipeline.store.add_publication(
                    title, doi, document_sha=hashlib.sha256(uploaded.getbuffer()).hexdigest())
                uploaded.seek(0)
                identifier = pipeline.collect(publication,uploaded)
                st.success(f"Registered document {identifier} for publication P{publication}.")
            if st.button("Process / resume next batch",key="corpus_process"):
                progress = st.progress(0.0)
                status = st.empty()

                def update(identifier,page,total):
                    progress.progress(page/total)
                    status.text(f"{identifier}: page {page}/{total}")

                outcome = pipeline.run(update)
                st.write(outcome or "No documents are queued.")
            st.caption(f"Each batch: at most {config.pages_per_run} pages, {config.documents_per_run} documents; "
                       f"{config.seconds_per_run}s soft deadline. Click again to continue after a checkpoint.")
            offset = st.number_input("Document list offset",min_value=0,step=50,key="corpus_offset")
            documents = pipeline.store.documents(offset=int(offset))
            st.dataframe(documents,use_container_width=True)
            st.caption("Semantic indexing is optional and uses only installed local embedding weights. "
                       "Run ollama pull all-minilm:latest first if you choose this feature.")
            if st.button("Index next local embedding batch",key="corpus_index"):
                with st.spinner("Computing local embeddings…"):
                    count = asyncio.run(retrieval.index())
                st.success(f"Indexed {count} passages; rerun for the next batch.")
            query = st.text_input("Find evidence",key="corpus_query")
            methods = {"Keyword": "keyword", "Local semantic": "semantic", "Hybrid": "hybrid"}
            mode = st.selectbox("Retrieval method",list(methods),key="corpus_mode")
            titles = {row["id"]: row["title"] for row in documents}
            document_ids = st.multiselect("Paper scope", list(titles), key="corpus_paper_scope",
                                          max_selections=8, placeholder="Entire corpus",
                                          format_func=lambda item: f"{titles[item]} ({item[:8]})")
            if st.button("Retrieve evidence",disabled=not query.strip(),key="corpus_search"):
                st.session_state["corpus_results"] = asyncio.run(service.search_evidence(
                    query, mode=methods[mode], document_ids=document_ids))
            if st.button("Answer scientific question", disabled=not query.strip(), key="corpus_ask"):
                st.session_state.pop("corpus_answer", None)
                try:
                    with st.spinner("Checking source evidence"):
                        st.session_state["corpus_answer"] = asyncio.run(service.ask_corpus(
                            query, mode=methods[mode], document_ids=document_ids))
                except TimeoutError:
                    st.error("The question exceeded the configured time limit.")
            if answer := st.session_state.get("corpus_answer"):
                if answer["status"] == "insufficient_evidence":
                    st.info("No relevant source excerpt was found for this question.")
                elif answer["status"] == "evidence_only":
                    st.warning("Relevant excerpts were found, but no generated scientific claim passed the support check.")
                elif answer["status"] == "partial_evidence":
                    st.warning("The available evidence answers only part of the question.")
                elif answer["status"] == "evidence_available":
                    st.caption("Extractive source evidence; semantic support has not been independently assessed.")
                elif answer["status"] == "model_checked_answer":
                    st.caption("Generated claims passed a bounded local-model support check; this is not human verification.")
                synthesized = [claim for claim in answer["claims"] if claim["kind"] != "source_excerpt"]
                if synthesized:
                    for claim in synthesized:
                        references = "; ".join(
                            f"{citation['title']}, PDF p. {citation['page']}"
                            for citation in claim["citations"]
                        )
                        st.markdown(f"{claim['claim']} *(Evidence: {references})*")
                elif answer.get("answer"):
                    st.markdown(answer["answer"])
                for part in answer.get("unanswered_parts", []):
                    st.text(f"Unanswered: {part}")
                st.caption(answer["coverage"])
                if answer.get("evidence"):
                    with st.expander("Original PDF evidence", expanded=False):
                        for item in answer["evidence"]:
                            citation = item["citation"]
                            st.text(f"{citation['title']} · PDF page {citation['page']} · Chunk {citation['chunk_id']}")
                            st.code(citation["quote"], language=None, wrap_lines=True)
                            st.caption(
                                f"SHA-256: {citation['sha256']} · Character offsets "
                                f"{citation['start_char']}–{citation['end_char']}"
                            )
                with st.expander("Retrieval and validation details"):
                    st.json(answer)
                st.download_button("Download answer JSON", json.dumps(answer, ensure_ascii=False, indent=2),
                                   "corpus-answer.json", "application/json")
            for cached in st.session_state.get("corpus_results",[]):
                try:
                    row = pipeline.store.evidence(cached["id"])
                except ValueError:
                    st.warning("An evidence record was reset. Run the search again.")
                    continue
                st.text(f"{evidence_reference(row)} {row['title']} — PDF page {row['page']}")
                st.code(row["text"],language=None)
                st.caption(f"SHA-256: {row['sha256']} · Character offsets {row['start_char']}–{row['end_char']} · "
                           f"DOI: {row['doi'] or 'not recorded'}")
        except (ValueError,OSError,sqlite3.Error) as exc:
            st.error(f"Corpus: {exc}")
