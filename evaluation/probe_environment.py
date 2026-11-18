"""Save non-secret dependency, model and input-file verification evidence."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

import httpx
from packaging.requirements import Requirement
import pymupdf

from research_swarm.config import ROOT, Settings
from research_swarm.providers import OllamaProvider


def run(output):
    dependencies = []
    for name in ("requirements.txt","requirements-mcp.txt"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith(("#","-")):
                continue
            requirement = Requirement(line)
            installed = importlib.metadata.version(requirement.name)
            valid = requirement.specifier.contains(installed)
            dependencies.append(dict(requirement=str(requirement),installed=installed,satisfied=valid))
            if not valid:
                raise RuntimeError(f"Unsatisfied dependency: {requirement.name}")
    pip_check = subprocess.run([sys.executable,"-m","pip","check"],capture_output=True,text=True,check=True)
    settings = Settings.from_env()
    if settings.provider != "ollama" or settings.local_test_mode:
        raise RuntimeError("Live verification requires configured local Ollama, not fixtures.")
    identity = asyncio.run(OllamaProvider(settings).identity())
    response = httpx.get(settings.ollama_url+"/api/ps",trust_env=False,timeout=10)
    response.raise_for_status()
    papers = []
    for paper in json.loads((ROOT / "evaluation" / "sources.json").read_text(encoding="utf-8")):
        path = ROOT / ".runtime" / "evaluation-papers" / (paper["id"] + ".pdf")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != paper["pdf_sha256"]:
            raise RuntimeError("Scientific paper checksum mismatch.")
        with pymupdf.open(path) as doc:
            pages = len(doc)
        papers.append(dict(id=paper["id"],pages=pages,sha256=checksum,source=paper["url"]))
    report = dict(python=platform.python_version(),dependencies=dependencies,
        pip_check=pip_check.stdout.strip(),model_identity=identity,ollama_running_models=response.json(),
        effective_settings={key:getattr(settings,key) for key in ("provider","model","local_test_mode",
            "prompt_variant","context_tokens","summary_context_tokens","ollama_gpu_layers")},papers=papers)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    run(parser.parse_args().output)
