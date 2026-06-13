import os, json, hashlib, numpy as np
from pathlib import Path

MODEL_NAME = os.environ.get('EMBEDDING_MODEL', 'BAAI/bge-small-en-v1.5')
INDEX_PATH = Path(os.environ.get('KNOWLEDGE_INDEX_PATH', '/home/liviyo/.knowledge_index'))

class KnowledgeBase:
    def __init__(self):
        self.model = None
        self.docs = []
        self.embeddings = None
        self.faiss_index = None
        self._load()

    def _get_model(self):
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(MODEL_NAME)
        return self.model

    def _load(self):
        INDEX_PATH.mkdir(parents=True, exist_ok=True)
        docs_file = INDEX_PATH / 'docs.json'
        if docs_file.exists():
            self.docs = json.loads(docs_file.read_text())
        index_file = INDEX_PATH / 'index.faiss'
        if index_file.exists():
            import faiss
            self.faiss_index = faiss.read_index(str(index_file))

    def _save(self):
        INDEX_PATH.mkdir(parents=True, exist_ok=True)
        (INDEX_PATH / 'docs.json').write_text(json.dumps(self.docs))
        if self.faiss_index:
            import faiss
            faiss.write_index(self.faiss_index, str(INDEX_PATH / 'index.faiss'))

    def index_text(self, text: str, source: str = ""):
        model = self._get_model()
        import faiss
        vec = model.encode([text], normalize_embeddings=True)
        if self.faiss_index is None:
            dim = vec.shape[1]
            self.faiss_index = faiss.IndexFlatIP(dim)
        self.faiss_index.add(vec)
        self.docs.append({"text": text, "source": source})
        self._save()
        return len(self.docs)

    def index_file(self, filepath: str) -> str:
        path = Path(filepath)
        if not path.exists():
            return f"File not found: {filepath}"
        if path.is_dir():
            count = 0
            for f in sorted(path.rglob('*')):
                if f.suffix in ('.txt', '.md', '.py', '.json', '.yaml', '.yml', '.csv', '.html', '.xml', '.cfg', '.ini', '.conf'):
                    try:
                        text = f.read_text(encoding='utf-8', errors='ignore')
                        if text.strip():
                            self.index_text(text[:5000], str(f))
                            count += 1
                    except:
                        pass
            return f"Indexed {count} files from {filepath}"
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
            self.index_text(text[:10000], filepath)
            return f"Indexed {filepath}"
        except:
            return f"Failed to index {filepath}"

    def search(self, query: str, k: int = 5) -> str:
        if self.faiss_index is None or self.faiss_index.ntotal == 0:
            return "Knowledge base is empty. Use [KNOWLEDGE_INDEX: path] to add documents first."
        model = self._get_model()
        qvec = model.encode([query], normalize_embeddings=True)
        scores, indices = self.faiss_index.search(qvec, min(k, self.faiss_index.ntotal))
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.docs):
                doc = self.docs[idx]
                results.append(f"[{scores[0][i]:.3f}] {doc.get('source', '?')}\n{doc['text'][:400]}")
        return "\n---\n".join(results)

    def stats(self) -> str:
        count = self.faiss_index.ntotal if self.faiss_index else 0
        sources = set(d.get('source','') for d in self.docs)
        return f"{count} documents indexed from {len(sources)} sources. Model: {MODEL_NAME}"

kb = KnowledgeBase()
