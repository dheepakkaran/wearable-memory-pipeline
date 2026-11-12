"""Retrieval over personal context: BM25 keyword baseline, pgvector embedding search, and a hybrid (RRF)."""
import re

import numpy as np
from rank_bm25 import BM25Okapi

from . import db
from .embed import embed_query

_tok = lambda s: re.findall(r"[a-z0-9']+", s.lower())


def _rows(conn, meeting=None):
    q = "SELECT capture_id, meeting_id, start_s, end_s, text FROM captures"
    return conn.execute(q + (" WHERE meeting_id=%s" if meeting else "") + " ORDER BY capture_id",
                        (meeting,) if meeting else ()).fetchall()


def bm25(conn, query, k=3, meeting=None):
    rows = _rows(conn, meeting)
    scores = BM25Okapi([_tok(r[4]) for r in rows]).get_scores(_tok(query))
    return [rows[i] for i in np.argsort(-scores)[:k]]


def vector(conn, query, k=3, meeting=None):
    v = np.array(embed_query(query))
    sql = "SELECT capture_id, meeting_id, start_s, end_s, text FROM captures"
    sql += (" WHERE meeting_id=%s" if meeting else "") + " ORDER BY embedding <=> %s LIMIT %s"
    return conn.execute(sql, ((meeting,) if meeting else ()) + (v, k)).fetchall()


def hybrid(conn, query, k=3, meeting=None, depth=20):
    ranks = {}
    for lst in (bm25(conn, query, depth, meeting), vector(conn, query, depth, meeting)):
        for i, r in enumerate(lst):
            ranks.setdefault(r[0], [r, 0.0])[1] += 1 / (60 + i)
    return [r for r, _ in sorted(ranks.values(), key=lambda x: -x[1])[:k]]


METHODS = {"bm25": bm25, "vector": vector, "hybrid": hybrid}


def search_memories(conn, query, k=3):
    v = np.array(embed_query(query))
    return conn.execute("SELECT kind, text, owner, due, meeting_id, capture_ids FROM memories "
                        "WHERE kind <> 'summary' ORDER BY embedding <=> %s LIMIT %s", (v, k)).fetchall()
