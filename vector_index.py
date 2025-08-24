import os
import json
import logging
import numpy as np
import threading
import time
from typing import Dict, List, Tuple, Optional
from supabase import Client as SupabaseClient

log = logging.getLogger("vector_index")

# Configurable refresh interval - set very high to disable hot-path refreshes
REFRESH_MIN_SECONDS = float(os.getenv("INDEX_REFRESH_MIN_SECONDS", "3600"))

try:
    import hnswlib
    HNSW_OK = True
    # Some versions don't have __version__ attribute
    version = getattr(hnswlib, '__version__', 'unknown')
    log.info("[HNSW] import successful: hnswlib version %s", version)
except Exception as e:
    HNSW_OK = False
    log.warning("[HNSW] import failed: %s", e)
    hnswlib = None

def _coerce_vec_any(v, dim=1536):
    """Coerce any embedding shape (list/tuple/np/string) and validate length"""
    # Already a list/tuple?
    if isinstance(v, (list, tuple)):
        arr = [float(x) for x in v]
    elif isinstance(v, str):
        s = v.strip()
        try:
            # pgvector via PostgREST usually returns JSON-like "[...]" -> json.loads
            if s.startswith('['):
                arr = [float(x) for x in json.loads(s)]
            elif s.startswith('(') and s.endswith(')'):
                # handle "(v1,v2,...)" -> split
                arr = [float(x) for x in s[1:-1].split(',')]
            else:
                # last resort: try json.loads anyway
                arr = [float(x) for x in json.loads(s)]
        except Exception as e:
            raise ValueError(f"cannot parse embedding string: {e}")
    else:
        # numpy or other
        try:
            arr = np.asarray(v, dtype="float32").tolist()
        except Exception as e:
            raise ValueError(f"unsupported embedding type {type(v)}: {e}")

    if len(arr) != dim:
        raise ValueError(f"bad embed length: got {len(arr)} expected {dim}")
    return arr

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
                clean = []
                for iid, vec in embeddings:
                    a = np.asarray(_coerce_vec_any(vec, DIM), dtype=np.float32)
                    n = np.linalg.norm(a) or 1.0
                    clean.append((iid, (a / n).tolist()))
                vecs = np.asarray([e[1] for e in clean], dtype=np.float32)
                print(f"[HNSW] rebuild(): validated and normalized {len(clean)} vectors, shape: {vecs.shape}")
            except Exception as e:
                print(f"[HNSW] rebuild(): vector validation failed: {e}")
                self._built = False
                return

            self.index = hnswlib.Index(space=SPACE, dim=DIM)
            self.index.init_index(max_elements=vecs.shape[0], ef_construction=EF_CONSTRUCT, M=M)
            labels = np.arange(vecs.shape[0])
            self.index.add_items(vecs, labels)
            ef_query = min(128, max(32, int(len(clean) * 0.4)))
            try:
                self.index.set_ef(ef_query)
            except Exception:
                pass  # keep it safe if backend version lacks set_ef
            self.labels = labels.tolist()
            self.intent_ids = [e[0] for e in clean]
            self._next_label = vecs.shape[0]
            self._built = True
            print(f"[HNSW] rebuild(): success, built index with {len(self.intent_ids)} vectors")



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
        self._last_version_check: Dict[str, float] = {}  # client_id -> last check time

    def warm(self):
        if not HNSW_OK:
            print("[HNSW] disabled: import failed")
            return
            
        print("[HNSW] warm(): fetching embeddings...")
        # Load all embeddings grouped by client
        rows = self._fetch_all_embeddings()
        print(f"[HNSW] warm(): fetched {len(rows)} rows")
        
        per_client: Dict[str, List[Tuple[str, List[float]]]] = {}
        bad = 0
        for r in rows:
            try:
                vec = _coerce_vec_any(r["embedding"], DIM)
                per_client.setdefault(r["client_id"], []).append((r["intent_id"], vec))
            except Exception as e:
                bad += 1
                print(f"[HNSW] warm(): skipped malformed embedding: {e}")
        if bad:
            print(f"[HNSW] warm(): skipped {bad} malformed embeddings")
            
        with self._lock:
            for cid, emb in per_client.items():
                print(f"[HNSW] building client={cid} count={len(emb)}")
                ci = self._by_client.get(cid) or ClientIndex()
                ci.rebuild(emb)
                self._by_client[cid] = ci
        self._last_refresh_at = time.time()
        
        # Warm-start "retry once" if a client is empty
        empty = [cid for cid, ci in self._by_client.items() if not ci._built or not ci.intent_ids]
        if empty:
            time.sleep(1.0)
            for cid in empty:
                try:
                    self.refresh_client(cid)
                except Exception as e:
                    print(f"[HNSW] warm retry failed for {cid}: {e}")
        
        print("[HNSW] warm(): done")

    def refresh_client(self, client_id: str):
        print(f"[HNSW] refresh_client({client_id})")
        rows = self._fetch_embeddings_for(client_id)
        ok = 0; bad = 0
        emb = []
        for r in rows:
            try:
                vec = _coerce_vec_any(r["embedding"], DIM)
                emb.append((r["intent_id"], vec))
                ok += 1
            except Exception as e:
                bad += 1
                print(f"[HNSW] refresh_client: skipped malformed embedding: {e}")
        print(f"[HNSW] refresh_client: ok={ok} bad={bad}")

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
        """Check if client index needs refresh based on version - only check every 5 minutes"""
        current_time = time.time()
        last_check = getattr(self, '_last_version_check', {}).get(client_id, 0)
        
        # Only check version every N minutes to avoid DB calls on every request
        if current_time - last_check < REFRESH_MIN_SECONDS:
            return False
            
        try:
            row = self.sb.table("intent_embedding").select("updated_at").eq("client_id", client_id).order("updated_at", desc=True).limit(1).single().execute()
            if hasattr(row, "error") and row.error:
                return True
            db_ts = row.data["updated_at"] if row.data else None
            cached = self._client_versions.get(client_id)
            
            # Update last check time
            if not hasattr(self, '_last_version_check'):
                self._last_version_check = {}
            self._last_version_check[client_id] = current_time
            
            if db_ts:
                self._client_versions[client_id] = db_ts
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
                print(f"[HNSW] topk(): still no index for {client_id}")
                return []
        
        pairs = ci.topk(vec, k)
        if not pairs:
            log.warning("[HNSW] WARN: empty ANN result, forcing refresh for %s", client_id)
            self.refresh_client(client_id)
            with self._lock:
                ci = self._by_client.get(client_id)
            pairs = ci.topk(vec, k) if ci else []
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
