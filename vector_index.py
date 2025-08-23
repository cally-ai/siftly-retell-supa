import hnswlib
import numpy as np
import threading
import time
from typing import Dict, List, Tuple, Optional
from supabase import Client as SupabaseClient

DIM = 1536  # text-embedding-3-small
M = 32      # graph degree
EF_CONSTRUCT = 200
SPACE = "cosine"

class ClientIndex:
    def __init__(self):
        self._lock = threading.RLock()
        self.index = hnswlib.Index(space=SPACE, dim=DIM)
        self.index.init_index(max_elements=1, ef_construction=EF_CONSTRUCT, M=M)  # init small; we'll resize
        self.index.set_ef(64)  # query time/accuracy
        self.labels: List[int] = []
        self.intent_ids: List[str] = []  # parallel array; label -> intent_id
        self._next_label = 0
        self._built = False

    def rebuild(self, embeddings: List[Tuple[str, List[float]]]):
        with self._lock:
            # embeddings: [(intent_id, vector), ...]
            if not embeddings:
                # empty index but keep object
                self.index = hnswlib.Index(space=SPACE, dim=DIM)
                self.index.init_index(max_elements=1, ef_construction=EF_CONSTRUCT, M=M)
                self.labels, self.intent_ids = [], []
                self._next_label, self._built = 0, True
                return

            vecs = np.asarray([e[1] for e in embeddings], dtype=np.float32)
            self.index = hnswlib.Index(space=SPACE, dim=DIM)
            self.index.init_index(max_elements=vecs.shape[0], ef_construction=EF_CONSTRUCT, M=M)
            labels = np.arange(vecs.shape[0])
            self.index.add_items(vecs, labels)
            self.index.set_ef(64)
            self.labels = labels.tolist()
            self.intent_ids = [e[0] for e in embeddings]
            self._next_label = vecs.shape[0]
            self._built = True

    def topk(self, vec: List[float], k: int) -> List[Tuple[str, float]]:
        with self._lock:
            if not self._built or not self.intent_ids:
                return []
            q = np.asarray([vec], dtype=np.float32)
            labels, dists = self.index.knn_query(q, k=min(k, len(self.intent_ids)))
            # hnswlib returns cosine distance (0 = identical). Convert to similarity = 1 - dist
            return [(self.intent_ids[l], float(1.0 - d)) for l, d in zip(labels[0], dists[0])]

class VectorIndexManager:
    def __init__(self, supabase: SupabaseClient):
        self.sb = supabase
        self._lock = threading.RLock()
        self._by_client: Dict[str, ClientIndex] = {}
        self._last_refresh_at = 0

    def warm(self):
        # Load all embeddings grouped by client
        rows = self._fetch_all_embeddings()
        per_client: Dict[str, List[Tuple[str, List[float]]]] = {}
        for r in rows:
            cid = r["client_id"]
            per_client.setdefault(cid, []).append((r["intent_id"], r["embedding"]))
        with self._lock:
            for cid, emb in per_client.items():
                ci = self._by_client.get(cid) or ClientIndex()
                ci.rebuild(emb)
                self._by_client[cid] = ci
        self._last_refresh_at = time.time()

    def refresh_client(self, client_id: str):
        rows = self._fetch_embeddings_for(client_id)
        emb = [(r["intent_id"], r["embedding"]) for r in rows]
        with self._lock:
            ci = self._by_client.get(client_id) or ClientIndex()
            ci.rebuild(emb)
            self._by_client[client_id] = ci

    def topk(self, client_id: str, vec: List[float], k: int) -> List[Dict]:
        with self._lock:
            ci = self._by_client.get(client_id)
        if not ci:
            # lazy build if needed
            self.refresh_client(client_id)
            with self._lock:
                ci = self._by_client.get(client_id)
            if not ci:
                return []
        pairs = ci.topk(vec, k)
        return [{"intent_id": iid, "similarity": sim} for iid, sim in pairs]

    # --- Supabase fetch helpers ---
    def _fetch_all_embeddings(self) -> List[dict]:
        # SELECT client_id, intent_id, embedding FROM intent_embedding;
        r = self.sb.table("intent_embedding").select("client_id,intent_id,embedding").execute()
        if hasattr(r, "error") and r.error:
            raise RuntimeError(r.error.message)
        return r.data or []

    def _fetch_embeddings_for(self, client_id: str) -> List[dict]:
        r = self.sb.table("intent_embedding").select("client_id,intent_id,embedding").eq("client_id", client_id).execute()
        if hasattr(r, "error") and r.error:
            raise RuntimeError(r.error.message)
        return r.data or []
