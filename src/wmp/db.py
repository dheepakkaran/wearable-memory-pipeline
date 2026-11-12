"""PostgreSQL + pgvector schema. Only redacted text is stored; raw audio is never written to the database."""
import psycopg
from pgvector.psycopg import register_vector

from .config import EMBED_DIM, PG_DSN

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS captures (
  capture_id   text PRIMARY KEY,
  device_id    text NOT NULL,
  meeting_id   text NOT NULL,
  start_s      double precision NOT NULL,
  end_s        double precision NOT NULL,
  text         text NOT NULL,           -- redacted transcript
  pii_spans    int NOT NULL DEFAULT 0,
  transcribe_ms double precision,
  e2e_ms       double precision,        -- button_up -> stored
  embedding    vector({EMBED_DIM}),
  created_at   timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS memories (
  id           serial PRIMARY KEY,
  meeting_id   text NOT NULL,
  kind         text NOT NULL CHECK (kind IN ('commitment','memory','summary')),
  text         text NOT NULL,
  owner        text,
  due          text,
  evidence     text,
  capture_ids  text[] NOT NULL DEFAULT '{{}}',
  model        text,
  status       text NOT NULL DEFAULT 'open',
  embedding    vector({EMBED_DIM}),
  created_at   timestamptz DEFAULT now()
);
"""


def connect():
    conn = psycopg.connect(PG_DSN, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def init(reset: bool = False):
    with connect() as c:
        if reset:
            c.execute("DROP TABLE IF EXISTS captures, memories")
        c.execute(SCHEMA)
