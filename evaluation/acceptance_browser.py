"""Exercise corpus controls against an actual Streamlit server in Chromium."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / ".runtime/browser-deps"))
from playwright.sync_api import sync_playwright

OUT = ROOT / os.environ.get("RAG_ACCEPTANCE_OUTPUT", "evaluation/results/final-acceptance")
OUT.mkdir(parents=True, exist_ok=True)
report = {"steps": [], "browser_errors": []}
work = ROOT / ".runtime" / ("acceptance-browser-" + uuid4().hex)
with socket.socket() as listener:
    listener.bind(("127.0.0.1",0))
    port = listener.getsockname()[1]
url = f"http://127.0.0.1:{port}"
command = [sys.executable,"-m","streamlit","run","app.py","--server.headless=true",
           "--server.address=127.0.0.1",f"--server.port={port}","--browser.gatherUsageStats=false"]
report["command"] = command
env = {**os.environ,"CORPUS_ROOT":str(work),"LOCAL_TEST_MODE":"false","ALLOW_PAID_API":"false",
       "LLM_PROVIDER":"ollama","LLM_CACHE_ENABLED":"false","LLM_TIMEOUT_SECONDS":"45"}
with (OUT / "streamlit-corpus-server.log").open("w", encoding="utf-8") as log:
    server = subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        with httpx.Client(trust_env=False,timeout=2) as client:
            for _ in range(100):
                try:
                    if client.get(url + "/_stcore/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Health endpoint never returned HTTP 200")
        report["steps"].append("health endpoint returned HTTP 200")
        with sync_playwright() as playwright:
            chrome = Path(os.environ["LOCALAPPDATA"]) / "ms-playwright/chromium-1255/chrome-win64/chrome.exe"
            browser = playwright.chromium.launch(executable_path=str(chrome),headless=True)
            page = browser.new_page(accept_downloads=True,viewport={"width":1400,"height":1120})
            page.on("pageerror",lambda error: report["browser_errors"].append(str(error)))
            page.goto(url,wait_until="domcontentloaded",timeout=45000)
            page.get_by_text("Research corpus",exact=False).first.click(timeout=30000)
            page.get_by_text("Enable corpus workspace",exact=True).click()
            for title, name in [("Adam: A Method for Stochastic Optimization", "1412.6980v9.pdf")]:
                page.get_by_label("Publication title").fill(title)
                page.get_by_label("Publication title").press("Tab")
                page.locator('input[type="file"]').last.set_input_files(str(ROOT / ".runtime/evaluation-papers" / name))
                page.get_by_role("button",name="Register PDF",exact=True).click()
                page.get_by_text("Registered document",exact=False).wait_for()
                page.get_by_role("button",name="Process / resume next batch").click()
                page.get_by_text("page 15/15",exact=False).first.wait_for(timeout=30000)
                report["steps"].append("uploaded and indexed " + name)
            search = page.get_by_label("Find evidence",exact=True)
            search.fill("adaptive estimates of lower-order moments")
            search.press("Tab")
            page.get_by_role("button",name="Retrieve evidence",exact=True).click()
            page.get_by_text("PDF page",exact=False).first.wait_for()
            report["steps"].append("retrieved and displayed evidence with PDF page")
            page.get_by_role("button",name="Answer scientific question",exact=True).click()
            deadline = time.monotonic()+130
            button = page.get_by_role("button",name="Download answer JSON")
            while time.monotonic() < deadline:
                if button.is_visible() or page.locator('[data-testid="stAlert"]').count() > 1:
                    break
                time.sleep(0.3)
            if button.is_visible():
                with page.expect_download() as download:
                    button.click()
                download.value.save_as(str(OUT / "streamlit-answer.json"))
                report["steps"].append("displayed and downloaded QA JSON")
            else:
                report["alerts"] = page.locator('[data-testid="stAlert"]').all_inner_texts()
            page.screenshot(path=str(OUT / "streamlit-corpus.png"),full_page=True)
            browser.close()
    except Exception as exc:
        report["failure"] = str(exc)
    finally:
        server.terminate()
        server.wait(timeout=15)
        (OUT / "streamlit-corpus.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(report)
