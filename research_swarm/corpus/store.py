"""Versioned SQLite metadata, checkpoints and exact page evidence."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from uuid import uuid4


def normalize_doi(doi: str | None):
    if not doi or not doi.strip():
        return None
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi.strip(), flags=re.I).casefold()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        raise ValueError("Enter a valid DOI or leave it empty; no DOI is inferred.")
    return doi


class CorpusStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported corpus schema version; use a compatible application.")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS publications (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, doi TEXT UNIQUE,
                    authors TEXT NOT NULL, year INTEGER, identity TEXT NOT NULL UNIQUE,
                    source_url TEXT, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, publication_id INTEGER NOT NULL REFERENCES publications(id),
                    sha256 TEXT NOT NULL UNIQUE, relative_path TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending', page_count INTEGER NOT NULL,
                    last_page INTEGER NOT NULL DEFAULT 0, profile TEXT,
                    owner TEXT, lease_until REAL, error TEXT, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS pages (
                    document_id TEXT NOT NULL REFERENCES documents(id), number INTEGER NOT NULL,
                    text TEXT NOT NULL, PRIMARY KEY(document_id, number));
                CREATE TABLE IF NOT EXISTS passages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL, page INTEGER NOT NULL,
                    start_char INTEGER NOT NULL, end_char INTEGER NOT NULL, section TEXT,
                    text TEXT NOT NULL, UNIQUE(document_id,page,start_char),
                    FOREIGN KEY(document_id,page) REFERENCES pages(document_id,number) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS passage_document ON passages(document_id,page);
                CREATE INDEX IF NOT EXISTS document_queue ON documents(status,updated);
                CREATE TABLE IF NOT EXISTS vectors (
                    passage_id INTEGER NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
                    model TEXT NOT NULL, dimensions INTEGER NOT NULL, vector BLOB NOT NULL,
                    PRIMARY KEY(passage_id,model));
                CREATE INDEX IF NOT EXISTS vector_model ON vectors(model,passage_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS passage_fts USING fts5(text, content='passages', content_rowid='id');
                CREATE TRIGGER IF NOT EXISTS passage_insert AFTER INSERT ON passages BEGIN
                    INSERT INTO passage_fts(rowid,text) VALUES (new.id,new.text); END;
                CREATE TRIGGER IF NOT EXISTS passage_delete AFTER DELETE ON passages BEGIN
                    INSERT INTO passage_fts(passage_fts,rowid,text) VALUES ('delete',old.id,old.text); END;
                CREATE TABLE IF NOT EXISTS retrieval_history (
                    id INTEGER PRIMARY KEY, query TEXT NOT NULL, mode TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL, created REAL NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_publication(self, title, doi=None, authors=(), year=None, source_url=None, *, document_sha=None):
        title = title.strip()
        if not title or len(title) > 2000:
            raise ValueError("A publication title of 1–2000 characters is required.")
        if year is not None and (type(year) is not int or not 1000 <= year <= 9999):
            raise ValueError("Publication year must be a four-digit integer or absent.")
        doi = normalize_doi(doi)
        authors = tuple(a.strip() for a in authors if a.strip())
        # Without a DOI, merge only a complete title/year/first-author identity.
        # Missing identifiers remain separate rather than guessing equivalence.
        normalized = " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", title).casefold()))
        identity = (hashlib.sha256(json.dumps(
            [normalized, year, authors[0].casefold()], ensure_ascii=False).encode()).hexdigest()
            if year and authors else f"doi:{doi}" if doi else f"pdf:{document_sha}" if document_sha else uuid4().hex)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if document_sha:
                document = db.execute("""SELECT p.id,p.doi FROM documents d
                    JOIN publications p ON p.id=d.publication_id WHERE d.sha256=?""", (document_sha,)).fetchone()
                if document:
                    if doi and doi != document["doi"]:
                        raise ValueError("This PDF is already registered with different DOI metadata.")
                    return document["id"]
            existing = db.execute("SELECT id,doi FROM publications WHERE doi=? OR identity=? ORDER BY doi=? DESC", (doi, identity,doi)).fetchone()
            if existing:
                if doi and existing["doi"] and doi != existing["doi"]:
                    raise ValueError("Conflicting DOI for the same publication identity; reconcile metadata manually.")
                if doi and not existing["doi"]:
                    db.execute("UPDATE publications SET doi=? WHERE id=?", (doi,existing["id"]))
                return existing[0]
            return db.execute("INSERT INTO publications(title,doi,authors,year,identity,source_url,created) VALUES (?,?,?,?,?,?,?)",
                              (title, doi, json.dumps(authors), year, identity, source_url, time.time())).lastrowid

    def document(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT d.*,p.title,p.doi FROM documents d JOIN publications p ON p.id=d.publication_id WHERE d.id=?",
                             (identifier,)).fetchone()
        if row is None:
            raise ValueError("Unknown document identifier.")
        return dict(row)

    def documents(self, limit=50, offset=0, pending_only=False):
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("Invalid document listing bounds.")
        with self.connect() as db:
            rows = db.execute("SELECT d.*,p.title FROM documents d JOIN publications p ON p.id=d.publication_id "
                              + ("WHERE d.status != 'complete' " if pending_only else "")
                              + "ORDER BY d.updated,d.id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return [dict(row) for row in rows]

    def evidence(self, identifier):
        return self.evidence_many([identifier])[0]

    def evidence_many(self, identifiers):
        """Load a bounded retrieval result in one connection, preserving rank."""
        identifiers = list(identifiers)
        if not identifiers:
            return []
        records = {}
        with self.connect() as db:
            # Stay below SQLite's variable limit even for larger callers.
            for start in range(0, len(identifiers), 500):
                batch = identifiers[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = db.execute("""SELECT e.*,p.id publication_id,p.title,p.doi,d.sha256,d.relative_path
                    FROM passages e JOIN documents d ON d.id=e.document_id
                    JOIN publications p ON p.id=d.publication_id WHERE e.id IN ("""
                    + placeholders + ")", batch).fetchall()
                records.update((row["id"], dict(row)) for row in rows)
        if any(identifier not in records for identifier in identifiers):
            raise ValueError("Unknown evidence identifier.")
        return [records[identifier].copy() for identifier in identifiers]

    def claim(self, identifier, profile, lease_seconds=120):
        owner = uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM documents WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise ValueError("Unknown document identifier.")
            if row["profile"] not in (None, profile):
                raise ValueError("Extraction settings changed. Reset this document before rebuilding its evidence.")
            if row["status"] == "complete" or (row["owner"] and (row["lease_until"] or 0) > time.time()):
                return None
            db.execute("UPDATE documents SET status='processing',owner=?,lease_until=?,profile=?,error=NULL,updated=? WHERE id=?",
                       (owner, time.time()+lease_seconds, profile, time.time(), identifier))
        return owner

    def commit_page(self, identifier, owner, number, text, passages):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner,last_page FROM documents WHERE id=?", (identifier,)).fetchone()
            if not row or row["owner"] != owner or number != row["last_page"] + 1:
                raise ValueError("Document lease/checkpoint changed; this worker must stop.")
            db.execute("INSERT INTO pages VALUES (?,?,?)", (identifier,number,text))
            db.executemany("INSERT INTO passages(document_id,page,start_char,end_char,section,text) VALUES (?,?,?,?,?,?)",
                           [(identifier,number,*passage) for passage in passages])
            db.execute("UPDATE documents SET last_page=?,lease_until=?,updated=? WHERE id=?",
                       (number,time.time()+120,time.time(),identifier))

    def release(self, identifier, owner, status, error=None):
        with self.connect() as db:
            db.execute("UPDATE documents SET status=?,error=?,owner=NULL,lease_until=NULL,updated=? WHERE id=? AND owner=?",
                       (status,error,time.time(),identifier,owner))

    def reset(self, identifier):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner,lease_until FROM documents WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise ValueError("Unknown document identifier.")
            if row["owner"] and (row["lease_until"] or 0) > time.time():
                raise ValueError("Cannot reset a document with an active worker.")
            db.execute("DELETE FROM pages WHERE document_id=?", (identifier,))
            db.execute("UPDATE documents SET status='pending',last_page=0,profile=NULL,owner=NULL,lease_until=NULL,error=NULL,updated=? WHERE id=?",
                       (time.time(),identifier))

    def record_retrieval(self, query, mode, identifiers):
        with self.connect() as db:
            db.execute("INSERT INTO retrieval_history(query,mode,evidence_ids,created) VALUES (?,?,?,?)",
                       (query,mode,json.dumps(identifiers),time.time()))
