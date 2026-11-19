# Professor demonstration

Run from the repository root in PowerShell. Keep Ollama available and the three pinned PDFs under `.runtime/evaluation-papers`.

```powershell
ollama list
$env:LLM_PROVIDER = 'ollama'
$env:OLLAMA_MODEL = 'llama3.2:latest'
$env:LOCAL_TEST_MODE = 'false'
$env:ALLOW_PAID_API = 'false'
.\.venv-swarm\Scripts\python.exe -m streamlit run app.py
```

In the corpus workspace, upload a PDF, enter its title, register it and process the next batch. Ask a BLEU question, then open the exact cited excerpt. Select the Transformer and LoRA PDFs to ask “What English-to-German BLEU did Transformer achieve and what GPU memory reduction did LoRA report?” Show both source quotations and describe the differences between their experiments. Use an unrelated clinical dropout question to show abstention. Export the answer JSON for inspection.

For an automated stdio walkthrough with a separate process and restart, run:

```powershell
$env:RAG_ACCEPTANCE_OUTPUT = 'evaluation/results/professor-reproduction'
.\.venv-swarm\Scripts\python.exe -m evaluation.acceptance_sdk --skip-specialists
.\.venv-swarm\Scripts\python.exe -m evaluation.acceptance_sdk --case comparison
```

The current corpus pilot supports this scenario with known limitations. The LoRA conclusion and false-premise failures are examples to discuss when explaining the difference between exact provenance and scientific applicability. [Quality notes](SCIENTIFIC_QUALITY_REPORT.md)
