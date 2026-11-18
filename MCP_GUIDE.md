# Local scientific-paper MCP server

The server uses the official Python MCP SDK and the existing PDF, Summary,
Questions, Literature and Orchestrator implementations. It does not import
Streamlit. All six tools have typed input/output schemas and structured results.

## Install and run

```powershell
.\.venv-swarm\Scripts\python.exe -m pip install -r requirements-mcp.txt
.\.venv-swarm\Scripts\python.exe -m research_swarm.mcp_server --pdf-root C:\papers
```

The verified optional SDK version is `mcp==2.3.0`. The existing Streamlit app
does not require this optional file. A stdio server waits silently for a client;
it is not an HTTP website. Logs go to stderr, and stdout is protocol-only.

Configure Ollama and optional paid access through the existing project `.env`
or process environment. The server retains all provider authorization guards.
It never accepts credentials, prompt file paths, or provider endpoints in tool
arguments. `LOCAL_TEST_MODE=true` invokes synthetic offline fixtures and labels
results `synthetic: true`; that mode is not research analysis.

## Tools

| Tool | Arguments | Behavior |
| --- | --- | --- |
| `extract_paper_text` | `pdf_path` | Actual physical page text, SHA-256 and extraction warnings |
| `summarize_paper` | `pdf_path`, optional `mode` | Existing SummaryAgent; partial or full-map coverage is disclosed |
| `find_research_questions` | `pdf_path` | SummaryAgent then QuestionsAgent, structured questions and source pages |
| `search_literature` | `questions` matching the existing Questions schema | OpenAlex metadata and structured title-only assessments |
| `analyze_paper` | `pdf_path`, optional `mode` | Complete existing Orchestrator, saved reports and validated scientific-paper data |
| `get_analysis_result` | returned `run_id` | Reload saved validated data without model calls |

`pdf_path` is relative to `--pdf-root`. Absolute paths, traversal outside the
root, non-PDF files and oversized files are rejected. The root is controlled by
the operator, not the client. Run IDs are validated before reading saved data.

`mode` is `FAST_RESEARCH_MODE` or `FULL_RESEARCH_MODE`. Standalone summary and
question tools use the existing direct-text selection behavior; full analysis
uses the Orchestrator's corpus-based FAST selection. These evidence selectors
are different and are disclosed rather than presented as equivalent.

Full analysis saves ordinary reports plus `analysis.json` beneath
`--output-root` (default `output/mcp/<run-id>/`). The JSON contains summary
Markdown, validated questions, structured literature records, coverage,
source pages/checksum, warnings, model name and prompt fingerprint. Physical
page references are source metadata; generated claims are not automatically
proven correct. Source text and results may contain sensitive information.

## Client configuration

Use absolute executable/project paths in clients that support stdio servers:

```json
{
  "mcpServers": {
    "research": {
      "command": "C:\\path\\to\\neuro\\.venv-swarm\\Scripts\\python.exe",
      "args": [
        "-m", "research_swarm.mcp_server",
        "--pdf-root", "C:\\papers"
      ],
      "cwd": "C:\\path\\to\\neuro"
    }
  }
}
```

The `cwd` field depends on the client's configuration format. If unsupported,
configure the client's subprocess working directory separately. The Python
example below is verified with the official SDK:

```python
import asyncio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

async def main():
    params = StdioServerParameters(
        command=r"C:\path\to\neuro\.venv-swarm\Scripts\python.exe",
        args=["-m", "research_swarm.mcp_server", "--pdf-root", r"C:\papers"],
        cwd=r"C:\path\to\neuro",
    )
    async with Client(params, read_timeout_seconds=700) as client:
        print((await client.list_tools()).tools)
        result = await client.call_tool("analyze_paper", {"pdf_path": "paper.pdf"})
        if result.is_error:
            print(result.content)
        else:
            print(result.structured_content)

asyncio.run(main())
```

## Limits

Analysis is a direct asynchronous tool call: configure a client timeout longer
than `DOCUMENT_TIMEOUT_SECONDS`. There is no new durable job scheduler.
Standalone summary/question/literature operations also share the document time
budget across their asynchronous calls. Reserved Windows device names and
alternate data streams are rejected before opening a PDF. Completed analysis
JSON is replaced atomically; saved-result paths remain inside the output root.
Existing
summary/page checkpoints remain, but a killed request is not automatically
resumed. Only one operation runs per server instance; another receives a busy
error. Cancelling the client does not immediately stop the underlying worker.
Do not run live Streamlit analysis and MCP analysis simultaneously on a small
GPU: there is no cross-process inference lock.

The server is local stdio only, not a multi-user authenticated service. No OCR,
hard native-memory sandbox, automatic full-text literature verification, or
claim-grounding guarantee is added. Full page text can produce large responses;
use small/medium readable papers within the existing configured limits.

## Verification and reproduction

```powershell
.\.venv-swarm\Scripts\python.exe -m pytest -q tests/test_mcp.py
# Real papers must first be downloaded by evaluation/prepare.py.
.\.venv-swarm\Scripts\python.exe -m evaluation.mcp_smoke --output evaluation/results/new-mcp-smoke.json
```

The automated subprocess tests use real PDF extraction and orchestration with
explicit offline fixtures. The separate smoke script uses a real local model,
a downloaded scientific PDF, and normal OpenAlex discovery. Inspect saved
warnings: an external search outage is partial success, not a verified search.
