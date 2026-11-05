"""Run with: python -m streamlit run app.py"""
import logging
from uuid import uuid4
from dataclasses import replace
import streamlit as st
from research_swarm.config import ROOT, Settings
from research_swarm.jobs import start_run, active, snapshot, saved_result, ARTIFACTS
from research_swarm.dashboard import render_dashboard

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# HTTP debug logs can contain credential-bearing URLs; keep them disabled.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

st.set_page_config(page_title="AI Research Agent Swarm", page_icon="📚", layout="wide")
st.title("AI Research Agent Swarm")
st.write("Upload a research PDF to generate a summary, research questions, and an OpenAlex literature review.")
st.caption("Readable text only; OCR is not implemented. Ollama runs AI locally by default; "
           "research queries go to OpenAlex. OpenAI requires explicit paid-API opt-in. "
           "LOCAL_TEST_MODE uses synthetic offline fixtures.")
uploaded = st.file_uploader("Research paper (PDF, up to 25 MB)", type=["pdf"])
research_mode=st.selectbox("Research mode",["FAST_RESEARCH_MODE","FULL_RESEARCH_MODE"],key="research_mode")
st.caption("FAST selects bounded source evidence. FULL processes every accepted chunk and can require multiple resumptions. "
           "Completed summary steps are saved in SQLite in both modes.")
run_id = st.session_state.get("analysis_run_id") or st.query_params.get("run")
running = bool(run_id and active(run_id))

if st.button("Start Analysis", type="primary", disabled=uploaded is None or running):
    st.session_state.pop("result", None)
    st.session_state.pop("partial", None)
    try:
        settings = replace(Settings.from_env(),research_mode=research_mode)
        if settings.local_test_mode:
            st.info("Offline testing mode: synthetic results, no AI or literature service calls.")
        else:
            st.info(f"LLM provider: {settings.provider} · Model: {settings.model}")
        new_id = uuid4().hex
        start_run(ROOT,new_id,settings,uploaded.getvalue())
        run_id = new_id
        st.session_state["analysis_run_id"] = run_id
        st.query_params["run"] = run_id
        st.rerun()  # One launch refresh disables Start and attaches the read-only dashboard.
    except (ValueError,OSError) as exc:
        st.error(str(exc))

if run_id:
    try:
        state = snapshot(ROOT,run_id)
        if state:
            render_dashboard(ROOT,run_id)
            if state["state"] == "completed":
                st.session_state["result"] = saved_result(ROOT,run_id)
                st.success("Analysis complete. Review inferred questions and title-based relevance before citing.")
            elif state["state"] in {"failed","interrupted"}:
                st.session_state.pop("result",None)
                partial = {}
                for name in ARTIFACTS:
                    try:
                        path = ROOT / "output" / run_id / name
                        if path.is_file():
                            partial[name] = path.read_text(encoding="utf-8")
                    except OSError:
                        st.warning(f"Could not read {name}; check output permissions .")
                st.session_state["partial"] = partial
    except (ValueError,OSError) as exc:
        st.error(f"Could not read progress checkpoint: {exc}")

result = st.session_state.get("result")
if result:
    for warning in result.warnings:
        st.warning(warning)
    st.caption(f"Saved to {result.output_dir}")
    for tab, name in zip(st.tabs(["Summary", "Research questions", "Literature"]),
                         ["summary.md", "open_questions.md", "literature_review.md"]):
        with tab:
            st.markdown(result.files[name])
    files = result.files
else:
    files = st.session_state.get("partial", {})
if files:
    st.subheader("Download generated files")
    for name, content in files.items():
        st.download_button(f"Download {name}", content, file_name=name,
                           mime="text/plain" if name.endswith(".txt") else "text/markdown")

from research_swarm.corpus.ui import render_corpus
render_corpus()
