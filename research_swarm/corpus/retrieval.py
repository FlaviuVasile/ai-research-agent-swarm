"""FTS5 plus optional local embeddings; persistent vectors, bounded exact scan."""
from array import array
import heapq
import math
import re
import time

import httpx

from research_swarm.config import Settings
from research_swarm.llm import chunks
from research_swarm.providers import OllamaProvider
from .config import CorpusConfig
from .query import query_search_terms
from .store import CorpusStore


def unit_vector(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 4096:
        raise ValueError("Invalid local embedding dimensions.")
    if any(type(value) not in (int,float) or not math.isfinite(value) for value in values):
        raise ValueError("Embedding must contain finite numeric values.")
    norm = math.sqrt(sum(value * value for value in values))
    if not norm or not math.isfinite(norm):
        raise ValueError("Embedding has invalid magnitude.")
    return [value / norm for value in values]


class LocalEmbeddings:
    def __init__(self, config: CorpusConfig):
        self.config = config
        # Never inherits OpenAI provider selection or credentials.
        self.guard = OllamaProvider(Settings(model=config.embedding_model, ollama_url=config.ollama_url))

    async def identity(self):
        return f"{await self.guard.identity()}:byte-segments-v1:{self.config.embedding_context}"

    async def _request(self, client, texts):
        response = await client.post("/api/embed", json={"model": self.config.embedding_model,
            "input": texts, "truncate": False, "keep_alive": "1m",
            "options": {"num_ctx": self.config.embedding_context}})
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError("Missing embedding rows")
        vectors = [unit_vector(row) for row in vectors]
        if len({len(row) for row in vectors}) != 1:
            raise ValueError("Inconsistent embedding dimensions")
        return vectors

    async def embed(self, texts):
        if not 1 <= len(texts) <= 16 or any(not text.strip() or len(text) > 2000 for text in texts):
            raise ValueError("Embedding batches require 1–16 nonempty passages, at most 2000 characters each.")
        await self.identity()
        try:
            # The embedding guard validates loopback HTTP; redirects remain disabled.
            async with httpx.AsyncClient(base_url=self.config.ollama_url, timeout=120,
                                         trust_env=False, follow_redirects=False, verify=False) as client:
                normalized = [" ".join(text.split()) for text in texts]
                if all(len(text.encode()) <= 120 for text in normalized):
                    return await self._request(client, normalized)
                # Keep segments below small native model limits and pool them so
                # every part of the passage contributes to its search vector.
                groups = [chunks(text, 120) for text in normalized]
                flat = [segment for group in groups for segment in group]
                vectors = []
                for start in range(0, len(flat), 16):
                    vectors.extend(await self._request(client, flat[start:start + 16]))
                if len({len(row) for row in vectors}) != 1:
                    raise ValueError("Inconsistent embedding dimensions")
                offset = 0
                pooled = []
                for group in groups:
                    block = vectors[offset:offset + len(group)]
                    pooled.append(unit_vector([sum(values) for values in zip(*block)]))
                    offset += len(group)
                return pooled
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            raise ValueError("Local embedding failed. Check the installed embedding model and passage size; no remote fallback used.") from None


class EvidenceRetrieval:
    def __init__(self, store: CorpusStore, config: CorpusConfig, embeddings=None):
        self.store, self.config = store, config
        self.embeddings = embeddings

    def _limit(self, limit):
        limit = self.config.retrieval_limit if limit is None else limit
        if not 1 <= limit <= 50:
            raise ValueError("Retrieval limit must be 1–50.")
        return limit

    def keyword(self, query, limit=None, publication_id=None, *, document_id=None, document_ids=(),
                 normalize_query=True):
        limit = self._limit(limit)
        if not query.strip() or len(query) > 1000:
            raise ValueError("Enter a query of 1–1000 characters.")
        words = (query_search_terms(query) if normalize_query
                 else re.findall(r"\w+", query, re.UNICODE))[:32]
        if not words:
            return []
        # Literal OR terms, not user-supplied FTS operators/SQL.
        match = " OR ".join('"' + word + '"' for word in words)
        params = [match]
        where = ""
        if publication_id is not None:
            where = " AND d.publication_id=?"
            params.append(publication_id)
        if document_id is not None:
            where += " AND d.id=?"
            params.append(document_id)
        if document_ids:
            where += " AND d.id IN (" + ",".join("?" for _ in document_ids) + ")"
            params.extend(document_ids)
        params.append(limit)
        with self.store.connect() as db:
            rows = db.execute("SELECT e.id,bm25(passage_fts) score FROM passage_fts JOIN passages e ON e.id=passage_fts.rowid "
                "JOIN documents d ON d.id=e.document_id WHERE passage_fts MATCH ?" + where + " ORDER BY score,e.id LIMIT ?", params).fetchall()
        results = [dict(evidence, score=-row["score"]) for row, evidence in zip(
            rows, self.store.evidence_many(row["id"] for row in rows))]
        self.store.record_retrieval(query,"keyword",[row["id"] for row in results])
        return results

    def _embedding_client(self):
        if self.embeddings is None:
            self.embeddings = LocalEmbeddings(self.config)
        return self.embeddings

    async def index(self, limit=None):
        client = self._embedding_client()
        identity = await client.identity()
        limit = self.config.embeddings_per_run if limit is None else limit
        if not 1 <= limit <= self.config.embeddings_per_run:
            raise ValueError("Embedding work must stay within CORPUS_EMBEDDINGS_PER_RUN.")
        count = 0
        deadline = time.monotonic() + self.config.seconds_per_run
        while count < limit and time.monotonic() < deadline:
            with self.store.connect() as db:
                rows = db.execute("SELECT id,text FROM passages WHERE NOT EXISTS "
                    "(SELECT 1 FROM vectors WHERE passage_id=passages.id AND model=?) ORDER BY id LIMIT ?",
                    (identity,min(8,limit-count))).fetchall()
            if not rows:
                break
            vectors = await client.embed([row["text"] for row in rows])
            if len(vectors) != len(rows):
                raise ValueError("Embedding response count mismatch.")
            vectors = [unit_vector(vector) for vector in vectors]
            with self.store.connect() as db:
                existing = db.execute("SELECT dimensions FROM vectors WHERE model=? LIMIT 1", (identity,)).fetchone()
                dimensions = len(vectors[0])
                if any(len(vector) != dimensions for vector in vectors) or (existing and existing[0] != dimensions):
                    raise ValueError("Embedding dimensions changed; use a distinct model identity.")
                for row, vector in zip(rows,vectors):
                    db.execute("INSERT OR IGNORE INTO vectors VALUES (?,?,?,?)",
                               (row["id"],identity,dimensions,array("f",vector).tobytes()))
            count += len(rows)
        return count

    async def semantic(self, query, limit=None, publication_id=None, *, document_id=None, document_ids=()):
        limit = self._limit(limit)
        if not query.strip() or len(query) > 1000:
            raise ValueError("Enter a query of 1–1000 characters.")
        client = self._embedding_client()
        identity = await client.identity()
        params = [identity]
        where = "v.model=?"
        if publication_id is not None:
            where += " AND d.publication_id=?"
            params.append(publication_id)
        if document_id is not None:
            where += " AND d.id=?"
            params.append(document_id)
        if document_ids:
            where += " AND d.id IN (" + ",".join("?" for _ in document_ids) + ")"
            params.extend(document_ids)
        with self.store.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM vectors v JOIN passages e ON e.id=v.passage_id "
                "JOIN documents d ON d.id=e.document_id WHERE " + where, params).fetchone()[0]
            if count > self.config.vector_scan_limit:
                raise ValueError("Vector scan limit exceeded. Filter by publication or configure a bounded larger scan.")
            if not count:
                raise ValueError("No vectors for this model. Run local semantic indexing first.")
            query_vector = unit_vector((await client.embed([query]))[0])
            cursor = db.execute("SELECT v.passage_id,v.dimensions,v.vector FROM vectors v JOIN passages e ON e.id=v.passage_id "
                "JOIN documents d ON d.id=e.document_id WHERE " + where, params)
            best = []
            while rows := cursor.fetchmany(128):
                for row in rows:
                    vector = array("f")
                    vector.frombytes(row["vector"])
                    if len(vector) != len(query_vector) or len(vector) != row["dimensions"]:
                        raise ValueError("Stored embedding dimensions do not match the query model.")
                    score = sum(a*b for a,b in zip(query_vector,vector))
                    item = (score,row["passage_id"])
                    if len(best) < limit:
                        heapq.heappush(best,item)
                    elif item > best[0]:
                        heapq.heapreplace(best,item)
        ranked = sorted(best, reverse=True)
        results = [dict(evidence, score=score) for (score, _), evidence in zip(
            ranked, self.store.evidence_many(identifier for _, identifier in ranked))]
        self.store.record_retrieval(query,"semantic",[row["id"] for row in results])
        return results

    async def search(self, query, *, mode="keyword", limit=None, document_id=None, document_ids=()):
        limit = self._limit(limit)
        if len(document_ids) > 8 or (document_id is not None and document_ids):
            raise ValueError("Select one document ID or up to eight document IDs.")
        for identifier in (document_id,) if document_id is not None else document_ids:
            self.store.document(identifier)
        scope = {"document_id": document_id, "document_ids": document_ids}
        if mode == "keyword":
            return self.keyword(query, limit, **scope)
        if mode == "semantic":
            return await self.semantic(query, limit, **scope)
        if mode != "hybrid":
            raise ValueError("Unknown retrieval method.")
        candidates = min(50, limit * 3)
        lexical = self.keyword(query, candidates, **scope)
        semantic = await self.semantic(query, candidates, **scope)
        scores, rows = {}, {}
        for ranking in (lexical, semantic):
            for rank, row in enumerate(ranking, 1):
                identifier = row["id"]
                rows[identifier] = row
                scores[identifier] = scores.get(identifier, 0) + 1 / (60 + rank)
        ranked = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))[:limit]
        self.store.record_retrieval(query, "hybrid", ranked)
        return [dict(rows[identifier], score=scores[identifier]) for identifier in ranked]


def evidence_reference(row):
    return f"[P{row['publication_id']}/D{row['document_id']}/p{row['page']}/E{row['id']}]"
