import os
import numpy as np
import threading
import time
from typing import Dict, List, Tuple, Optional
from supabase import Client as SupabaseClient

try:
    import hnswlib
    HNSW_OK = True
    print(f"[HNSW] import successful: hnswlib version {hnswlib.__version__}")
except Exception as e:
    HNSW_OK = False
    print(f"[HNSW] import failed: {e}")
    hnswlib = None

DIM = 1536  # text-embedding-3-small
M = 32      # graph degree
EF_CONSTRUCT = 200
SPACE = "cosine"

class ClientIndex:
    def __init__(self):
        self._lock = threading.RLock()
        if not HNSW_OK:
            self.index = None
            self.labels: List[int] = []
            self.intent_ids: List[str] = []
            self._next_label = 0
            self._built = False
            return
            
        self.index = hnswlib.Index(space=SPACE, dim=DIM)
        self.index.init_index(max_elements=1, ef_construction=EF_CONSTRUCT, M=M)  # init small; we'll resize
        self.index.set_ef(64)  # query time/accuracy
        self.labels: List[int] = []
        self.intent_ids: List[str] = []  # parallel array; label -> intent_id
        self._next_label = 0
        self._built = False

    def rebuild(self, embeddings: List[Tuple[str, List[float]]]):
        print(f"[HNSW] rebuild(): n={len(embeddings)}")
        
        with self._lock:
            if not HNSW_OK:
                print("[HNSW] rebuild(): disabled, HNSW not available")
                self._built = False
                return
                
            # embeddings: [(intent_id, vector), ...]
            if not embeddings:
                # empty index but keep object
                self.index = hnswlib.Index(space=SPACE, dim=DIM)
                self.index.init_index(max_elements=1, ef_construction=EF_CONSTRUCT, M=M)
                self.labels, self.intent_ids = [], []
                self._next_label, self._built = 0, True
                print("[HNSW] rebuild(): empty index created")
                return

            # Validate and coerce vectors
            try:
                clean = [(iid, self._coerce_vec(vec)) for iid, vec in embeddings]
                vecs = np.asarray([e[1] for e in clean], dtype=np.float32)
                print(f"[HNSW] rebuild(): validated {len(clean)} vectors, shape: {vecs.shape}")
            except Exception as e:
                print(f"[HNSW] rebuild(): vector validation failed: {e}")
                self._built = False
                return

            self.index = hnswlib.Index(space=SPACE, dim=DIM)
            self.index.init_index(max_elements=vecs.shape[0], ef_construction=EF_CONSTRUCT, M=M)
            labels = np.arange(vecs.shape[0])
            self.index.add_items(vecs, labels)
            self.index.set_ef(64)
            self.labels = labels.tolist()
            self.intent_ids = [e[0] for e in clean]
            self._next_label = vecs.shape[0]
            self._built = True
            print(f"[HNSW] rebuild(): success, built index with {len(self.intent_ids)} vectors")

    def _coerce_vec(self, v):
        """Flatten and validate vector dimensions"""
        # Flatten once if needed
        if isinstance(v, (list, tuple)) and len(v) == 1 and isinstance(v[0], (list, tuple)):
            v = v[0]
        v = [float(x) for x in v]
        if len(v) != DIM:
            raise ValueError(f"bad embed length: got {len(v)} expected {DIM}")
        return v

    def topk(self, vec: List[float], k: int) -> List[Tuple[str, float]]:
        with self._lock:
            if not HNSW_OK or not self._built or not self.intent_ids:
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
        self._client_versions: Dict[str, str] = {}  # client_id -> last_updated_at

    def warm(self):
        if not HNSW_OK:
            print("[HNSW] disabled: import failed")
            return
            
        print("[HNSW] warm(): fetching embeddings...")
        # Load all embeddings grouped by client
        rows = self._fetch_all_embeddings()
        print(f"[HNSW] warm(): fetched {len(rows)} rows")
        
        per_client: Dict[str, List[Tuple[str, List[float]]]] = {}
        for r in rows:
            cid = r["client_id"]
            per_client.setdefault(cid, []).append((r["intent_id"], r["embedding"]))
            
        with self._lock:
            for cid, emb in per_client.items():
                print(f"[HNSW] building client={cid} count={len(emb)}")
                ci = self._by_client.get(cid) or ClientIndex()
                ci.rebuild(emb)
                self._by_client[cid] = ci
        self._last_refresh_at = time.time()
        print("[HNSW] warm(): done")

    def refresh_client(self, client_id: str):
        rows = self._fetch_embeddings_for(client_id)
        emb = [(r["intent_id"], r["embedding"]) for r in rows]
        with self._lock:
            ci = self._by_client.get(client_id) or ClientIndex()
            ci.rebuild(emb)
            self._by_client[client_id] = ci
            
        # Update version timestamp
        try:
            row = self.sb.table("intent_embedding").select("updated_at").eq("client_id", client_id).order("updated_at", desc=True).limit(1).single().execute()
            if not (hasattr(row, "error") and row.error) and row.data:
                self._client_versions[client_id] = row.data["updated_at"]
        except Exception:
            pass

    def _needs_refresh(self, client_id: str) -> bool:
        """Check if client index needs refresh based on version"""
        try:
            row = self.sb.table("intent_embedding").select("updated_at").eq("client_id", client_id).order("updated_at", desc=True).limit(1).single().execute()
            if hasattr(row, "error") and row.error:
                return True
            db_ts = row.data["updated_at"] if row.data else None
            cached = self._client_versions.get(client_id)
            return cached is None or (db_ts and db_ts > cached)
        except Exception:
            return True

    def topk(self, client_id: str, vec: List[float], k: int) -> List[Dict]:
        with self._lock:
            ci = self._by_client.get(client_id)
        
        # Check if refresh is needed (version-based)
        if self._needs_refresh(client_id):
            self.refresh_client(client_id)
            with self._lock:
                ci = self._by_client.get(client_id)
        
        if not ci:
            print(f"[HNSW] topk(): cold client {client_id} -> refreshing")
            # lazy build if needed
            self.refresh_client(client_id)
            with self._lock:
                ci = self._by_client.get(client_id)
            if not ci:
                print(f"[HNSW] topk(): client {client_id} not built -> returning []")
                return []
        
        if not ci._built:
            print(f"[HNSW] topk(): client {client_id} not built -> returning []")
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
