"""Map/reduce summarization covers every accepted chunk."""
from research_swarm.llm import LLM, chunks
from research_swarm.config import Settings
from research_swarm.telemetry import emit, cache_flag
from time import perf_counter
import hashlib
import json
from research_swarm.budgets import timeboxed, document_budget
from research_swarm.summary_work import utf8_prefix

SUMMARY = ("Produce concise academic Markdown with headings Research topic, Objectives, "
           "Methodology, Findings, Conclusions, and Limitations. Say 'Not reported' when absent. "
           "Preserve page references when present. Retain explicit limitations and future work. "
           "Do not confuse cited background studies with this paper's findings. "
           "Keep the entire response below 180 words, using concise bullets.")

class SummaryAgent:
    def __init__(self, llm: LLM, settings: Settings, journal=None, selected_evidence=None) -> None:
        self.llm, self.settings = llm, settings
        self.journal,self.selected_evidence=journal,selected_evidence
        self.notes_path=None

    async def summarize(self, text: str) -> tuple[str, str]:
        with document_budget(self.settings.document_timeout):
            return await timeboxed(self._summarize(text),self.settings.document_timeout,"Summary document")

    async def _summarize(self,text):
        parts = chunks(text, self.settings.chunk_tokens)
        full=self.settings.research_mode=="FULL_RESEARCH_MODE"
        if full and len(parts) > self.settings.max_chunks:
            raise ValueError(f"PDF exceeds the {self.settings.max_chunks}-chunk cost limit. "
                             "Use a shorter PDF or deliberately raise MAX_CHUNKS.")
        raw_total=len(parts)
        identity=(await self.llm.provider.identity()) if isinstance(self.llm,LLM) else self.settings.model
        source=hashlib.sha256(text.encode()).hexdigest()
        profile=hashlib.sha256(json.dumps({"version":2,"provider":identity,"mode":self.settings.research_mode,
            "output":self.settings.summary_output_tokens,"context":self.settings.summary_context_tokens,
            "chunk":self.settings.chunk_tokens},sort_keys=True).encode()).hexdigest()
        if not full:
            if self.selected_evidence:
                selected=self.selected_evidence
            else:
                # Direct-text callers lack a PDF reference. Select bounded, spread
                # excerpts and label the partial coverage rather than invent citations.
                count=min(len(parts),self.settings.fast_evidence_limit)
                indices=sorted(set(round(i*(len(parts)-1)/max(1,count-1)) for i in range(count)))
                per=max(40,(self.settings.chunk_tokens-100)//max(1,len(indices)))
                selected=utf8_prefix("Selected direct-text excerpts only; not exhaustive.\n"+
                    "\n".join(utf8_prefix(parts[i],per) for i in indices),self.settings.chunk_tokens)
            parts=[selected]
        emit("summary_plan",total=len(parts),mode=self.settings.research_mode,raw_total=raw_total)
        notes = []
        compact=("Write concise academic Markdown in at most 70 words. Use only the supplied evidence. "
                 "Retain page/evidence references. Distinguish findings, limitations and missing information. "
                 "Do not infer automotive capabilities without supporting evidence. ")
        instructions=compact + ("Summarize this source chunk." if full else
            "FAST_RESEARCH_MODE: summarize only the selected excerpts. Explicitly label coverage as partial.")
        async def step(name,prompt,evidence,legacy=False):
            key=name+":"+hashlib.sha256((prompt+evidence).encode()).hexdigest()
            saved=self.journal.get(source,profile,key) if self.journal else None
            legacy_hit=False
            if saved is None and legacy and isinstance(self.llm,LLM):
                saved=await self.llm.legacy_summary(SUMMARY,evidence)
                legacy_hit=saved is not None
            if saved:
                cache_flag(True)
                if self.journal:
                    self.journal.save(source,profile,key,saved,0,"legacy_cache_import" if legacy_hit else "reused")
                return saved
            started=perf_counter()
            try:
                result=(await self.llm.run("Summary Agent",prompt,evidence,max_output_tokens=self.settings.summary_output_tokens,
                                          context_tokens=self.settings.summary_context_tokens)
                        if isinstance(self.llm,LLM) else await self.llm.run("Summary Agent",prompt,evidence))
                result=str(result)
                if not result.strip():
                    raise ValueError("Summary response was empty; no checkpoint was committed.")
                if self.journal:
                    self.journal.save(source,profile,key,result,perf_counter()-started)
                return result
            except BaseException:
                if self.journal:
                    self.journal.failed(source,profile,key,perf_counter()-started)
                raise
        for index, part in enumerate(parts,1):
            emit("chunk_start",index=index)
            cache_flag(False)
            started = perf_counter()
            notes.append(await step(f"chunk-{index}",instructions,part,legacy=full))
            if full and self.notes_path:
                self.notes_path.write_text("# Completed full-mode chunk notes\n\n"+
                    "\n\n".join(f"## Chunk {i}\n\n{note}" for i,note in enumerate(notes,1)),encoding="utf-8")
            emit("chunk_complete",index=index,seconds=perf_counter()-started,cached=cache_flag())
        if full and len(notes)>1:
            # One bounded final synthesis, not recursive re-summarization. All
            # full-mode map notes remain intact in the SQLite journal.
            count=min(6,len(notes))
            indices=sorted(set(round(i*(len(notes)-1)/max(1,count-1)) for i in range(count)))
            per=max(1,(self.settings.chunk_tokens-200)//len(indices)-20)
            digest=utf8_prefix("Selected, spread excerpts of full-mode notes; final synthesis is lossy. All detailed notes are checkpointed.\n"+
                "\n".join(f"Chunk {i+1}: "+utf8_prefix(notes[i],per) for i in indices),self.settings.chunk_tokens)
            emit("reduction_plan",round=1,total=1)
            emit("reduction_start",index=1)
            summary=await step("final",compact+"Synthesize these bounded chunk-note excerpts; label omitted detail.",digest)
            emit("reduction_complete",index=1)
        else:
            summary=notes[0]
        coverage=(f"FULL_RESEARCH_MODE: {raw_total} source chunks processed; final synthesis uses selected bounded note excerpts."
                  if full else f"FAST_RESEARCH_MODE: selected evidence only; {raw_total} raw chunks were not exhaustively summarized.")
        summary=f"> {coverage}\n\n"+summary
        # Short PDFs give Agent 3 verbatim text; long PDFs give a whole-document digest.
        evidence = (self.selected_evidence or parts[0]) if not full else text if raw_total == 1 else (
            "Hierarchical evidence digest of all PDF chunks (not verbatim text):\n" + summary)
        return summary, evidence
