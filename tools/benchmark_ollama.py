"""Bounded live Ollama workflow benchmark; run from the repository root."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import pymupdf
from orchestrator import Orchestrator
from research_swarm.config import Settings, ROOT
from research_swarm.telemetry import observe

async def main(label):
    folder = ROOT / 'output' / 'ollama-latency-benchmark' / label
    if folder.exists():
        raise ValueError('Use a new label so durable summary checkpoints cannot affect measurements.')
    folder.mkdir(parents=True)
    settings = replace(Settings.from_env(), provider='ollama', local_test_mode=False,
        allow_paid_api=False, openai_key='', openalex_key='', cache_enabled=False,
        research_db=folder / 'corpus.sqlite3', max_questions=1, papers_per_question=1)
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), 'Automotive scheduling: synthetic research example.\n'
            'Objective: compare QNX and Embedded Linux scheduling.\n'
            'Method: one simulated workload, without hardware measurements.\n'
            'Finding: no measured platform performance can be inferred.\n'
            'Limitation: real hardware timing and AUTOSAR integration need further study.')
        data = pdf.tobytes()
    (folder / 'input.pdf').write_bytes(data)
    requests, stages = [], []
    current = None
    def event(kind, **fields):
        nonlocal current
        if kind == 'request_start':
            current = dict(agent=fields['agent'], started=perf_counter())
            requests.append(current)
        elif kind == 'response' and current and fields.get('characters') and 'first_token_seconds' not in current:
            current['first_token_seconds'] = perf_counter() - current['started']
        elif kind == 'request_metrics' and current:
            current.update(fields)
        elif kind == 'request_end' and current:
            current['wall_seconds'] = perf_counter() - current.pop('started')
            print(json.dumps(current), flush=True)
    original_send = httpx.AsyncClient.send
    async def send(client, request, **kwargs):
        if request.url.path == '/api/chat':
            body = json.loads(request.content)
            if '--gpu-layers' in sys.argv:
                body['options']['num_gpu'] = int(sys.argv[sys.argv.index('--gpu-layers') + 1])
                request = httpx.Request(request.method, request.url, headers={k:v for k,v in request.headers.items() if k != 'content-length'}, json=body)
            if current is not None:
                current.update(context=body['options']['num_ctx'], output_limit=body['options']['num_predict'], gpu_layers=body['options'].get('num_gpu', 'auto'))
        return await original_send(client, request, **kwargs)
    if '--cold' in sys.argv:
        async with httpx.AsyncClient(base_url=settings.ollama_url, trust_env=False) as client:
            response = await client.post('/api/generate', json={'model':settings.model, 'keep_alive':0})
            response.raise_for_status()
    started = perf_counter()
    result = None
    error = None
    try:
        with observe(event), patch('httpx.AsyncClient.send', send):
            result = await Orchestrator(settings, folder).run(data,
                lambda stage, status: stages.append(dict(stage=stage,status=status,seconds=perf_counter()-started)))
    except Exception as exc:
        error = str(exc)
    report = dict(label=label, model=settings.model, cache_enabled=False,
        summary_context=settings.summary_context_tokens, context=settings.context_tokens,
        cold_start="--cold" in sys.argv,
        workload='Generated one-page synthetic PDF; one question, one real OpenAlex paper maximum',
        wall_seconds=perf_counter()-started, requests=requests, stages=stages,
        warnings=result.warnings if result else [], error=error,
        files=list(result.files) if result else [])
    (folder / 'timings.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
