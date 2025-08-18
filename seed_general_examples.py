import os
from dotenv import load_dotenv
from supabase import create_client
from openai import OpenAI

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
CLIENT_ID = os.environ["CLIENT_ID"]  # <-- matches your schema

EXAMPLES = [
  "What's your warranty?",
  "How long does installation usually take?",
  "Do you install home batteries?",
  "Can you add an EV charger to an existing system?",
  "Do you handle permits and inspections?",
  "What roof types can you work with?",
  "Do panels work on flat roofs?",
  "Do you offer system monitoring?",
  "What's included in the quote?",
  "Do you remove and reinstall panels for roof work?",
  "Do you service systems you didn't install?",
  "How often should panels be cleaned?",
  "What's the typical payback period?",
  "Do you offer financing options?",
  "Do you provide a site survey?"
]

def vec_literal(a): 
    return "[" + ",".join(str(x) for x in a) + "]"

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    oa = OpenAI(api_key=OPENAI_API_KEY)

    # Find General Question intent by slug for this client
    r = sb.table("intent").select("id").eq("client_id", CLIENT_ID)\
         .eq("slug", "general_question").single().execute()
    GENERAL_ID = r.data["id"]

    # Skip duplicates
    existing = sb.table("intent_example").select("text").eq("intent_id", GENERAL_ID).execute().data or []
    have = {row["text"] for row in existing}

    rows = []
    for txt in EXAMPLES:
        if txt in have:
            continue
        emb = oa.embeddings.create(model="text-embedding-3-small", input=txt).data[0].embedding
        rows.append({"intent_id": GENERAL_ID, "text": txt, "embedding": vec_literal(emb)})

    if rows:
        sb.table("intent_example").insert(rows).execute()
        print(f"Inserted {len(rows)} examples for intent {GENERAL_ID}")
    else:
        print("No new examples to insert.")

if __name__ == "__main__":
    main()
