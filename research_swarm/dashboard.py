"""Read-only Streamlit fragment; percentages represent committed work only."""
import streamlit as st
import math
from research_swarm.jobs import snapshot, measurements, STAGES


def duration(seconds):
    if seconds is None:
        return "Estimating..."
    seconds = max(0,int(seconds))
    hours,seconds = divmod(seconds,3600)
    minutes,seconds = divmod(seconds,60)
    return f"{hours:d}h {minutes:02d}m {seconds:02d}s" if hours else f"{minutes:d}m {seconds:02d}s"


def render_dashboard(root, run_id):
    initial = snapshot(root,run_id)
    if initial is None:
        st.warning("No saved progress was found for this run.")
        return

    @st.fragment(run_every="1s" if initial["state"] == "running" else None)
    def panel():
        data = snapshot(root,run_id)
        measured = measurements(data)
        summary = data["summary"]
        st.subheader("Research progress")
        st.caption(f"Run {run_id} · {data['provider']} · {data['model']} · Status: {data['state']}")
        history=data.get("request_history",[])
        completed=[row for row in history if row["state"]=="completed"]
        if history:
            average=sum(row.get("wall_seconds",0) for row in completed)/len(completed) if completed else 0
            st.caption(f"Recorded uncached requests: {len(history)} · Completed: {len(completed)} · "
                       f"Mean completed request: {average:.1f}s. Request history is saved with progress.")
        if data.get("checkpoint_error"):
            st.warning(data["checkpoint_error"])
        st.progress(measured["completed_stages"]/4,
                    text=f"Workflow milestones: {measured['completed_stages']} of 4 agents completed")
        st.caption("This bar counts completed agents; it is not a percentage of processing time.")
        elapsed,estimate = st.columns(2)
        elapsed.metric("Elapsed time",duration(measured["elapsed"]))
        eta = measured["chunk_eta"]
        eta_label = "Estimating..." if eta is None else ("~" + duration(math.ceil(eta)) if eta > 0 else duration(0))
        estimate.metric("Estimated remaining input-chunk time",eta_label)
        st.caption("Total workflow remaining: " + ("0m 00s" if data["state"] == "completed"
                   else "stopped" if data["state"] in {"failed","interrupted"}
                   else "Estimating... — future synthesis/search work is not yet measurable."))
        st.caption("Chunk ETA uses comparable completed, uncached calls. Later synthesis and agents are excluded; "
                   "total workflow remaining time is not yet measurable.")
        st.markdown(f"**Current activity:** {data['activity']}")
        if summary["total"]:
            fast=summary.get("mode")=="FAST_RESEARCH_MODE"
            st.progress(summary["completed"]/summary["total"],
                        text=f"{'Selected evidence summaries' if fast else 'Summary input chunks'}: "
                             f"{summary['completed']} of {summary['total']} completed")
            if fast:
                st.caption(f"FAST_RESEARCH_MODE: selected evidence only; {summary.get('raw_total')} raw chunks were not exhaustively summarized.")
            if summary["current"] is not None:
                if data["state"] == "running":
                    st.caption(f"Chunk {summary['current']} is in progress and is not included in the completed count.")
                else:
                    st.caption(f"Chunk {summary['current']} did not complete and is not included in the completed count.")
            if summary["phase"] == "reduction":
                st.progress(summary["reduction_completed"]/summary["reduction_total"],
                            text=f"Synthesis pass {summary['reduction_round']}: "
                                 f"{summary['reduction_completed']} of {summary['reduction_total']} groups completed")
                st.caption("All input chunks may be complete while Summary Agent is still synthesizing them.")
        else:
            st.caption("Summary chunk count: waiting for document validation and chunk planning.")
        request = data.get("request")
        if measured["request_elapsed"] is not None:
            st.info(f"{request['agent']} request is still running — {duration(measured['request_elapsed'])}. "
                    f"Received {request['characters']:,} response characters in {request['fragments']:,} stream messages. "
                    "No request completion percentage is available.")
        if measured["stalled"]:
            st.warning(f"No {data['provider']} response data for at least 60 seconds. The model may be loading or the request may be stalled. "
                       "The active chunk has not been marked complete; the configured timeout remains in force.")
        for stage in STAGES:
            st.markdown(f"**{stage}:** {data['stages'][stage]}")
        if data.get("error"):
            st.error(data["error"])
        if data["state"] in {"completed","failed","interrupted"} and st.session_state.get("dashboard_terminal_run") != run_id:
            st.session_state["dashboard_terminal_run"] = run_id
            st.rerun()  # Exactly one full refresh to load files and stop the polling timer.

    panel()
