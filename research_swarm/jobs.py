"""One bounded background analysis worker; atomic, private per-run checkpoints."""
import asyncio
from contextlib import suppress
from copy import deepcopy
import json
from pathlib import Path
import re
import statistics
import threading
import time
from uuid import uuid4

from research_swarm.models import AnalysisResult
from research_swarm.telemetry import observe

STAGES = ("PDF Master", "Summary Agent", "Open Questions Finder", "Literature Search Agent")
ARTIFACTS = ("extracted_text.txt", "summary.md", "open_questions.md", "literature_review.md","summary_chunks.md")
_registry = {}
_registry_lock = threading.RLock()


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    for attempt in range(5):
        try:
            temporary.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.02*(attempt+1))


class ProgressRecord:
    def __init__(self, directory, run_id, provider="ollama", model=""):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.lock = threading.RLock()
        now = time.time()
        self.data = {"version":1,"run_id":run_id,"provider":provider,"model":model,
            "state":"running","started_at":now,"updated_at":now,"finished_at":None,
            "stages":{stage:"waiting" for stage in STAGES},"stage":None,"activity":"Preparing analysis",
            "summary":{"total":0,"completed":0,"current":None,"phase":"waiting", "durations":[],
                       "reduction_round":0,"reduction_total":0,"reduction_completed":0},
            "request":None,"request_history":[],"error":None}
        self.flush()

    def flush(self):
        with self.lock:
            self.data["updated_at"] = time.time()
            self.data.pop("checkpoint_error",None)
            try:
                atomic_json(self.directory / "progress.json",self.data)
            except OSError:
                self.data["checkpoint_error"] = ("Progress could not be saved to disk. Live counters are available, "
                    "but recovery after a server restart is not guaranteed. Check output permissions and disk space.")

    def stage(self, name, status):
        with self.lock:
            if name not in self.data["stages"]:
                return
            state = "completed" if status.startswith("complete") else status
            self.data["stages"][name] = state
            self.data["stage"] = name
            self.data["activity"] = f"{name}: {state}"
            self.flush()

    def event(self, kind, **fields):
        with self.lock:
            summary = self.data["summary"]
            now = time.time()
            if kind == "summary_plan":
                summary.update(total=fields["total"],completed=0,phase="chunks")
                summary.update(mode=fields.get("mode","FULL_RESEARCH_MODE"),raw_total=fields.get("raw_total",fields["total"]))
            elif kind == "chunk_start":
                summary.update(current=fields["index"],phase="chunks")
                self.data["activity"] = f"Summarizing chunk {fields['index']} of {summary['total']}"
            elif kind == "chunk_complete":
                summary["completed"] = fields["index"]
                summary["current"] = None
                if not fields.get("cached"):
                    summary["durations"] = (summary["durations"] + [fields["seconds"]])[-6:]
            elif kind == "reduction_plan":
                summary.update(phase="reduction",reduction_round=fields["round"],
                               reduction_total=fields["total"],reduction_completed=0,current=None)
            elif kind == "reduction_start":
                self.data["activity"] = (f"Synthesizing summaries: pass {summary['reduction_round']}, "
                                         f"group {fields['index']} of {summary['reduction_total']}")
            elif kind == "reduction_complete":
                summary["reduction_completed"] = fields["index"]
            elif kind == "activity":
                self.data["activity"] = fields["text"]
            elif kind == "request_start":
                self.data["request"] = {"agent":fields["agent"],"started_at":now,
                    "last_response_at":None,"characters":0,"fragments":0,"cached":False,"state":"running",
                    "sequence":len(self.data["request_history"])+1,"phase":summary["phase"],"chunk":summary["current"],
                    "reduction_round":summary["reduction_round"]}
            elif kind == "request_metrics":
                if self.data["request"]:
                    self.data["request"].update(fields)
            elif kind == "response":
                request = self.data["request"]
                if request and request["state"] == "running":
                    request["last_response_at"] = now
                    request["characters"] += fields.get("characters",0)
                    request["fragments"] += 1
                return  # Heartbeat persists at most once a second during token flow.
            elif kind in {"request_end","cache_hit","request_failed"}:
                if kind == "cache_hit":
                    self.data["request"] = {"agent":fields["agent"],"started_at":now,"finished_at":now,
                        "last_response_at":None,"characters":0,"fragments":0,"cached":True,"state":"completed"}
                request = self.data["request"]
                if request:
                    was_running=request["state"]=="running"
                    request.update(state="failed" if kind == "request_failed" else "completed",
                                   cached=kind == "cache_hit",finished_at=now)
                    request["wall_seconds"]=now-request["started_at"]
                    if fields.get("active_seconds") is not None:
                        request["active_seconds"]=fields["active_seconds"]
                    if kind!="cache_hit" and was_running:
                        self.data["request_history"].append(dict(request))
                    elif kind=="request_failed" and self.data["request_history"] and request.get("sequence"):
                        if self.data["request_history"][-1].get("sequence")==request["sequence"]:
                            self.data["request_history"][-1]=dict(request)
            self.flush()

    def finish(self, state, error=None):
        with self.lock:
            self.data.update(state=state,error=error,finished_at=time.time())
            if state == "completed":
                for stage in STAGES:
                    self.data["stages"][stage] = "completed"
                self.data["activity"] = "Analysis complete"
            else:
                self.data["activity"] = "Analysis interrupted" if state == "interrupted" else "Analysis failed"
                for stage, status in self.data["stages"].items():
                    if status == "running":
                        self.data["stages"][stage] = "failed"
                if self.data["request"] and self.data["request"]["state"] == "running":
                    self.data["request"].update(state="failed",finished_at=self.data["finished_at"])
                    self.data["request"]["wall_seconds"]=self.data["finished_at"]-self.data["request"]["started_at"]
                    self.data["request_history"].append(dict(self.data["request"]))
            self.flush()


def active(run_id):
    with _registry_lock:
        job = _registry.get(run_id)
        return bool(job and job["thread"].is_alive())


def start_run(root, run_id, settings, pdf, controller_factory=None):
    if not re.fullmatch(r"[a-f0-9]{32}",run_id):
        raise ValueError("Invalid run identifier.")
    if not pdf or len(pdf) > settings.max_pdf_bytes:
        raise ValueError("Upload a nonempty PDF no larger than the configured 25 MB limit.")
    directory = Path(root) / "output" / run_id
    with _registry_lock:
        if active(run_id):
            return  # Idempotent attachment; never launch another analysis on refresh.
        if (directory / "progress.json").exists():
            raise ValueError("This run already exists. Start a new analysis explicitly to process again.")
        if any(job["thread"].is_alive() for job in _registry.values()):
            raise ValueError("Another analysis is running. This local GPU worker accepts one analysis at a time.")
        recorder = ProgressRecord(directory,run_id,settings.provider,settings.model)
        recorder.data["limits"]={"request_seconds":settings.llm_timeout,"document_seconds":settings.document_timeout,
            "summary_output_tokens":settings.summary_output_tokens,"research_mode":settings.research_mode}
        recorder.flush()

        def work():
            from orchestrator import Orchestrator, AnalysisError
            factory = controller_factory or Orchestrator

            async def execute():
                async def heartbeat():
                    while True:
                        await asyncio.sleep(1)
                        recorder.flush()
                pulse = asyncio.create_task(heartbeat())
                try:
                    with observe(recorder.event):
                        return await factory(settings,directory).run(pdf,recorder.stage)
                finally:
                    pulse.cancel()
                    with suppress(asyncio.CancelledError):
                        await pulse
            try:
                result = asyncio.run(execute())
                for name, content in result.files.items():
                    if name in ARTIFACTS and not (directory / name).exists():
                        (directory / name).write_text(content,encoding="utf-8")
                atomic_json(directory / "result.json",{"warnings":result.warnings,"files":[n for n in result.files if n in ARTIFACTS]})
                recorder.finish("completed")
            except Exception as exc:
                message = str(exc) if isinstance(exc,(AnalysisError,ValueError)) else "Analysis failed. Check local services and output permissions."
                recorder.finish("failed",message)
        thread = threading.Thread(target=work,name=f"research-{run_id[:8]}",daemon=True)
        # Drop old inactive handles; no PDF, credentials or result text is retained here.
        for key in list(_registry):
            if len(_registry) < 20:
                break
            if not active(key):
                del _registry[key]
        _registry[run_id] = {"thread":thread,"record":recorder}
        thread.start()


def snapshot(root, run_id):
    if not re.fullmatch(r"[a-f0-9]{32}",run_id or ""):
        return None
    with _registry_lock:
        job = _registry.get(run_id)
        if job:
            with job["record"].lock:
                data = deepcopy(job["record"].data)
                if data["state"] != "running" or job["thread"].is_alive():
                    return data
    path = Path(root) / "output" / run_id / "progress.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["state"] == "running":
        # No worker exists in this process. Freeze at the last persisted heartbeat.
        data.update(state="interrupted",finished_at=data["updated_at"],
                    activity="Analysis interrupted",
                    error="The server worker stopped. Progress and completed files were retained; no request was replayed. Start a new analysis explicitly to continue using cached results.")
        for stage,status in data["stages"].items():
            if status == "running":
                data["stages"][stage] = "failed"
        try:
            atomic_json(path,data)
        except OSError:
            data["checkpoint_error"] = "Saved progress is readable, but the interruption status could not be saved. Check output permissions."
        if job:
            with job["record"].lock:
                job["record"].data = data
    return data


def saved_result(root, run_id):
    if not re.fullmatch(r"[a-f0-9]{32}",run_id or ""):
        raise ValueError("Invalid run identifier.")
    directory = Path(root) / "output" / run_id
    metadata = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    if (not isinstance(metadata,dict) or not isinstance(metadata.get("files"),list)
            or not all(isinstance(n,str) for n in metadata["files"])
            or not isinstance(metadata.get("warnings"),list)
            or not all(isinstance(w,str) for w in metadata["warnings"])):
        raise ValueError("Invalid saved result metadata; completed files remain on disk.")
    files = {name:(directory / name).read_text(encoding="utf-8") for name in metadata["files"] if name in ARTIFACTS}
    return AnalysisResult(files,metadata["warnings"],str(directory))


def measurements(data, now=None, stall_seconds=60):
    now = time.time() if now is None else now
    end = data.get("finished_at") or now
    request = data.get("request")
    running = data["state"] == "running" and request and request["state"] == "running"
    request_elapsed = max(0,end-request["started_at"]) if running else None
    stalled = bool(running and now-(request["last_response_at"] or request["started_at"]) >= stall_seconds)
    summary = data["summary"]
    eta = None
    samples = summary["durations"]
    # Warm-up is excluded when enough samples exist, and cache hits never train ETA.
    comparable = samples[1:] if len(samples) > 3 else samples
    if data["state"] == "running" and summary["phase"] == "chunks" and len(comparable) >= 3 and not stalled:
        mean = statistics.mean(comparable)
        if mean > .05 and statistics.pstdev(comparable)/mean <= .5:
            remaining = summary["total"]-summary["completed"]
            elapsed = request_elapsed or 0
            if remaining > 0 and elapsed <= mean * 2:
                forecast = mean * remaining-elapsed
                eta = forecast if forecast > 0 else None
    if summary["total"] and summary["completed"] == summary["total"]:
        eta = 0  # All input chunks are actually complete; synthesis remains separate.
    return {"elapsed":max(0,end-data["started_at"]),"request_elapsed":request_elapsed,
            "stalled":stalled,"chunk_eta":eta,
            "completed_stages":sum(s == "completed" for s in data["stages"].values())}
