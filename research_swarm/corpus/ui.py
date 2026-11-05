"""Optional corpus workspace, leaving the original single-paper interface intact."""
import asyncio
import sqlite3
import streamlit as st
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
            if st.session_state.get("corpus_database") != str(config.database.resolve()):
                st.session_state.pop("corpus_results",None)
                st.session_state["corpus_database"] = str(config.database.resolve())
            st.caption("Local metadata and page evidence. Import only PDFs you are entitled to store. "
                       "Discovery, automatic downloads and comparative reports are planned phases.")
            title = st.text_input("Publication title",key="corpus_title")
            doi = st.text_input("DOI (optional; never inferred)",key="corpus_doi")
            uploaded = st.file_uploader("Import a local PDF to deCitit/",type=["pdf"],key="corpus_pdf")
            if st.button("Register PDF",disabled=uploaded is None or not title.strip(),key="corpus_register"):
                publication = pipeline.store.add_publication(title,doi)
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
            st.dataframe(pipeline.store.documents(offset=int(offset)),use_container_width=True)
            st.caption("Semantic indexing is optional and uses only installed local embedding weights. "
                       "Run ollama pull all-minilm:latest first if you choose this feature.")
            if st.button("Index next local embedding batch",key="corpus_index"):
                with st.spinner("Computing local embeddings…"):
                    count = asyncio.run(retrieval.index())
                st.success(f"Indexed {count} passages; rerun for the next batch.")
            query = st.text_input("Find evidence",key="corpus_query")
            mode = st.selectbox("Retrieval method",["Keyword", "Local semantic"],key="corpus_mode")
            if st.button("Retrieve evidence",disabled=not query.strip(),key="corpus_search"):
                rows = (retrieval.keyword(query) if mode == "Keyword"
                        else asyncio.run(retrieval.semantic(query)))
                st.session_state["corpus_results"] = rows
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
