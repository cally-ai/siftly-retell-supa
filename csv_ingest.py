#!/usr/bin/env python3
"""
CSV FAQ Ingestion Script
Bulk imports FAQ data from CSV file with embeddings
"""

import os, csv, re, argparse, sys, time
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

oa = OpenAI(api_key=OPENAI_API_KEY)
sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

def is_uuid(x: str) -> bool:
    return bool(x and UUID_RE.match(x))

def vec_literal(arr):
    # Convert Python list[float] -> pgvector text literal "[a,b,c,...]"
    return "[" + ",".join(str(x) for x in arr) + "]"

def embed(text: str, model: str) -> str:
    e = oa.embeddings.create(model=model, input=text).data[0].embedding
    return vec_literal(e)

def parse_tags(val: str | None) -> list[str]:
    if not val: return ["general"]
    # Allow "battery,general" or '["battery","general"]'
    v = val.strip()
    if v.startswith("[") and v.endswith("]"):
        # naive JSON-ish split without importing json
        v = v.strip("[]")
    return [t.strip().strip('"').strip("'") for t in v.split(",") if t.strip()]

def main():
    ap = argparse.ArgumentParser(description="Ingest FAQs into kb_documents/kb_chunks")
    ap.add_argument("csv_path", help="Path to CSV with columns: title,answer[,locale][,tags][,client_id]")
    ap.add_argument("--client-id", help="UUID to use for ALL rows (omit if CSV has client_id column)")
    ap.add_argument("--model", default="text-embedding-3-small", help="Embedding model (1536-dim)")
    ap.add_argument("--locale", default="en", help="Default locale if missing in CSV")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    args = ap.parse_args()

    # Validate client id if provided
    if args.client_id and not is_uuid(args.client_id):
        print("ERROR: --client-id must be a UUID", file=sys.stderr); sys.exit(1)

    required_cols = {"title","answer"}
    with open(args.csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = required_cols - set([c.strip() for c in reader.fieldnames or []])
        if missing:
            print(f"ERROR: CSV missing required columns: {missing}", file=sys.stderr); sys.exit(1)

        has_client_col = "client_id" in reader.fieldnames

        if not has_client_col and not args.client_id:
            print("ERROR: Provide --client-id OR include a client_id column in the CSV.", file=sys.stderr)
            sys.exit(1)

        ok = 0; fail = 0
        for i, row in enumerate(reader, start=1):
            title = (row.get("title") or "").strip()
            answer = (row.get("answer") or "").strip()
            locale = (row.get("locale") or args.locale).strip() or "en"
            tags = parse_tags(row.get("tags"))

            client_id = (row.get("client_id") or args.client_id or "").strip()
            if not is_uuid(client_id):
                print(f"[row {i}] SKIP: invalid client_id: {client_id!r}", file=sys.stderr)
                fail += 1; continue

            if not title or not answer:
                print(f"[row {i}] SKIP: title/answer empty", file=sys.stderr)
                fail += 1; continue

            try:
                v = embed(answer, args.model)
                payload = {
                    "p_client": client_id,
                    "p_title": title,
                    "p_answer": answer,
                    "p_embedding": v,
                    "p_locale": locale,
                    "p_tags": tags,
                    "p_metadata": {"source":"faq","question":title}
                }
                if args.dry_run:
                    print(f"[row {i}] DRY-RUN upsert {title!r} for client {client_id}")
                else:
                    res = sb.rpc("kb_upsert_faq", payload).execute()
                    doc_id = (res.data if isinstance(res.data, str) else res.data[0] if res.data else None)
                    print(f"[row {i}] OK  doc_id={doc_id}  title={title}")
                ok += 1
                # gentle pacing for rate limits
                time.sleep(0.05)
            except Exception as e:
                print(f"[row {i}] FAIL {title!r}: {e}", file=sys.stderr)
                fail += 1

        print(f"Done. OK={ok} FAIL={fail}")

if __name__ == "__main__":
    main()
