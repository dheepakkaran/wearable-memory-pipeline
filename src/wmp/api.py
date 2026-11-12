"""App layer: device ingestion + what the phone app / voice reply would call."""
from fastapi import Body, FastAPI, HTTPException, Query

from . import db
from .events import Event
from .ingest import client, ingest
from .retrieve import METHODS, search_memories

app = FastAPI(title="Wearable Voice Memory Pipeline")
_r = client()


@app.get("/healthz")
def healthz():
    _r.ping()
    return {"ok": True}


@app.post("/events")
def post_events(events: list[Event] = Body(...)):
    if len(events) > 64:
        raise HTTPException(413, "max 64 events per request")
    return ingest(_r, events)


@app.get("/ask")
def ask(q: str = Query(min_length=2), k: int = 3, method: str = "hybrid"):
    if method not in METHODS:
        raise HTTPException(400, f"method must be one of {list(METHODS)}")
    with db.connect() as c:
        hits = METHODS[method](c, q, k)
        mems = search_memories(c, q, k)
    return {"captures": [{"capture_id": h[0], "meeting_id": h[1], "start_s": h[2], "text": h[4]} for h in hits],
            "memories": [{"kind": m[0], "text": m[1], "owner": m[2], "due": m[3], "meeting_id": m[4],
                          "capture_ids": m[5]} for m in mems]}


@app.get("/today")
def today(meeting_id: str | None = None):
    """Open commitments: what the wearer promised and has not closed yet."""
    sql = "SELECT id, meeting_id, text, owner, due, capture_ids FROM memories WHERE kind='commitment' AND status='open'"
    with db.connect() as c:
        rows = c.execute(sql + (" AND meeting_id=%s" if meeting_id else "") + " ORDER BY meeting_id, id",
                         (meeting_id,) if meeting_id else ()).fetchall()
    return [{"id": r[0], "meeting_id": r[1], "text": r[2], "owner": r[3], "due": r[4], "capture_ids": r[5]} for r in rows]


@app.get("/summary/{meeting_id}")
def summary(meeting_id: str):
    with db.connect() as c:
        row = c.execute("SELECT text FROM memories WHERE kind='summary' AND meeting_id=%s", (meeting_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no summary yet (batch job not run)")
    return {"meeting_id": meeting_id, "summary": row[0]}
