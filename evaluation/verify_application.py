"""Launch Streamlit and exercise a real upload/model pipeline in Chromium."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
# Browser dependencies are isolated from the application environment.
sys.path.insert(0, str(ROOT / ".runtime" / "browser-deps"))
from playwright.sync_api import sync_playwright


def run(output, wait_for_experiment=None):
    if output.exists():
        raise ValueError("Choose a new verification report filename.")
    work = ROOT / ".runtime" / ("browser-verification-" + uuid4().hex)
    work.mkdir(parents=True)
    pdf = ROOT / ".runtime" / "evaluation-papers" / "1412.6980v9.pdf"
    if not pdf.is_file():
        raise ValueError("Run evaluation/prepare.py first to obtain the real Adam paper.")
    # Ask the OS for an unused loopback port rather than disrupting an existing app.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1",0))
        port = listener.getsockname()[1]
    env = {**os.environ,"LOCAL_TEST_MODE":"false","LLM_PROVIDER":"ollama","ALLOW_PAID_API":"false",
        "LLM_CACHE_ENABLED":"false","MAX_QUESTIONS":"1","PAPERS_PER_QUESTION":"1",
        "PROMPT_VARIANT":"selected","CORPUS_ROOT":str(work / "corpus"),
        "LLM_TIMEOUT_SECONDS":"120","DOCUMENT_TIMEOUT_SECONDS":"600"}
    command = [sys.executable,"-m","streamlit","run",str(ROOT / "app.py"),"--server.headless=true",
        "--server.address=127.0.0.1",f"--server.port={port}","--browser.gatherUsageStats=false"]
    report = dict(command=command,paper=pdf.name,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        model="llama3.2:latest",provider="ollama",prompt_variant="selected",synthetic=False,
        controlled_limits={"max_questions":1,"papers_per_question":1},errors=[])
    started = time.perf_counter()
    output.parent.mkdir(parents=True,exist_ok=True)
    log_path = work / "streamlit.log"
    process = None
    try:
        with log_path.open("w",encoding="utf-8") as log:
            process = subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            url = f"http://127.0.0.1:{port}"
            with httpx.Client(trust_env=False,timeout=2) as client:
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError("Streamlit exited before readiness; inspect its saved log.")
                    try:
                        if client.get(url + "/_stcore/health").status_code == 200:
                            report["health_ok"] = True
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError("Streamlit readiness timed out.")
            print("Streamlit health OK",flush=True)
            with sync_playwright() as playwright:
                chrome = Path(os.environ["LOCALAPPDATA"]) / "ms-playwright" / "chromium-1255" / "chrome-win64" / "chrome.exe"
                browser = playwright.chromium.launch(headless=True,executable_path=str(chrome))
                page = browser.new_page(accept_downloads=True,viewport={"width":1440,"height":1100})
                page.on("pageerror",lambda error: report["errors"].append(str(error)))
                # Streamlit maintains live connections; readiness is a rendered control,
                # not an idle network. This also avoids waiting on background traffic.
                page.goto(url,wait_until="domcontentloaded",timeout=45000)
                page.get_by_role("heading",name="AI Research Agent Swarm",exact=True).wait_for(timeout=30000)
                print("Application controls rendered",flush=True)
                report["initial_page_rendered"] = True
                page.locator('input[type="file"]').first.set_input_files(str(pdf))
                if wait_for_experiment:
                    print("Real browser upload OK; waiting for prompt experiment to release GPU",flush=True)
                    wait_deadline = time.monotonic()+3600
                    while time.monotonic() < wait_deadline:
                        try:
                            experiment = json.loads(wait_for_experiment.read_text(encoding="utf-8"))
                            if len(experiment["rows"]) == 27:
                                break
                        except (OSError,ValueError):
                            pass
                        time.sleep(2)
                    else:
                        raise RuntimeError("Prompt experiment did not finish before browser wait deadline.")
                page.get_by_role("button",name="Start Analysis",exact=True).click()
                deadline = time.monotonic()+650
                last_state = None
                while time.monotonic() < deadline:
                    run_id = parse_qs(urlsplit(page.url).query).get("run",[None])[0]
                    if run_id:
                        checkpoint = ROOT / "output" / run_id / "progress.json"
                        if checkpoint.exists():
                            state = json.loads(checkpoint.read_text(encoding="utf-8"))
                            status = (state["state"],state["stage"])
                            if status != last_state:
                                print("Application",status,flush=True)
                                last_state = status
                            if state["state"] in {"failed","interrupted"}:
                                raise RuntimeError(state.get("error") or "Application analysis failed.")
                    if page.get_by_text("Analysis complete. Review inferred questions and title-based relevance before citing.",exact=True).count():
                        report["run_id"] = run_id
                        report["progress"] = state
                        break
                    if page.get_by_test_id("stException").count():
                        raise RuntimeError(page.get_by_test_id("stException").inner_text())
                    page.wait_for_timeout(1000)
                else:
                    raise RuntimeError("Browser analysis completion timed out.")
                assert page.get_by_role("tab").count() == 3
                report["report_tabs"] = []
                for name in ("Summary","Research questions","Literature"):
                    page.get_by_role("tab",name=name,exact=True).click()
                    report["report_tabs"].append(name)
                report["downloads"] = []
                directory = ROOT / "output" / report["run_id"]
                for name in ("extracted_text.txt","summary.md","open_questions.md","literature_review.md"):
                    with page.expect_download(timeout=30000) as pending:
                        page.get_by_role("button",name="Download " + name,exact=True).click()
                    downloaded = pending.value
                    path = work / name
                    downloaded.save_as(path)
                    # Text downloads use LF; Windows text files may use CRLF.
                    # Compare decoded text with universal newline handling.
                    assert path.read_text(encoding="utf-8") == (directory / name).read_text(encoding="utf-8"), name
                    report["downloads"].append(dict(name=name,bytes=path.stat().st_size,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),matches_saved=True,
                        comparison="UTF-8 text with universal newline normalization"))
                assert not report["errors"]
                report["warnings"] = json.loads((directory / "result.json").read_text(encoding="utf-8"))["warnings"]
                report["application_complete"] = True
                page.screenshot(path=str(output.with_suffix(".png")),full_page=True)
                browser.close()
    except Exception as exc:
        report["errors"].append(str(exc))
        raise
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        report["seconds"] = time.perf_counter()-started
        report["server_log"] = str(log_path)
        report["server_stopped"] = process is not None and process.poll() is not None
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k not in {"progress","command"}}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--wait-for-experiment",type=Path)
    args = parser.parse_args()
    run(args.output,args.wait_for_experiment)
