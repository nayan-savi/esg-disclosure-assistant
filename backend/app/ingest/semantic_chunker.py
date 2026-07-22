import re
import math
import time
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document

VSME_CLASSIFICATIONS = {
    "B1": "B1 – Company Information & Reporting Declaration",
    "B2": "B2 – Sustainability Policies and Practices",
    "B3": "B3 – Energy and GHG Register",
    "B4": "B4 – Pollution Register",
    "B5": "B5 – Biodiversity Assessment",
    "B6": "B6 – Water Consumption Register",
    "B7": "B7 – Resource Use, Circular Economy & Waste Management",
    "B8": "B8 – Workforce General Characteristics",
    "B9": "B9 – Health & Safety Incident Register",
    "B10": "B10 – Employee Training & Remuneration Report",
    "B11": "B11 – Anti-Corruption & Bribery Compliance Report",
    "C1": "C1 – Sustainability Strategy Report",
    "C2": "C2 – ESG Policy Manual",
    "C3": "C3 – Climate Transition Plan",
    "C4": "C4 – Climate Risk Assessment",
    "C5": "C5 – Workforce Diversity Report",
    "C6": "C6 – Human Rights Due Dilence Report",
    "C7": "C7 – Human Rights Incident Register",
    "C8": "C8 – Revenue by Business Activities Report",
    "C9": "C9 – Governance Diversity Report",
}

class RateLimitedEmbeddings:
    """
    A wrapper around LangChain embeddings that batch-splits large requests,
    injects cooldown delays, and implements exponential backoff to handle
    API rate limits (like Gemini 100 RPM quota).
    """
    def __init__(self, embeddings: Any, max_retries: int = 5, batch_size: int = 15):
        self.embeddings = embeddings
        self.max_retries = max_retries
        self.batch_size = batch_size

    def _embed_with_retry(self, fn, *args, **kwargs):
        delay = 2.0
        for attempt in range(self.max_retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                err_str = str(e)
                if any(x in err_str or x in err_str.lower() for x in ["RESOURCE_EXHAUSTED", "429", "quota", "503", "unavailable", "temporarily"]):
                    print(f"Embedding API rate limit or transient error hit. Retrying in {delay:.1f}s (attempt {attempt+1}/{self.max_retries})...")
                    time.sleep(delay)
                    delay = min(delay * 2.0, 15.0)
                else:
                    raise e
        # Final try
        return fn(*args, **kwargs)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        results = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i+self.batch_size]
            batch_results = self._embed_with_retry(self.embeddings.embed_documents, batch)
            results.extend(batch_results)
            # Add a small delay between batches to stay safe
            if i + self.batch_size < len(texts):
                time.sleep(1.0)
        return results

    def embed_query(self, text: str) -> List[float]:
        return self._embed_with_retry(self.embeddings.embed_query, text)

class VSMESemanticChunker:
    """
    A semantic chunker that splits document text into chunks based on 
    the semantic similarity between consecutive sentences, and then tags 
    each chunk with the most relevant VSME ESG classification.
    """
    def __init__(
        self,
        embeddings: Any,
        breakpoint_percentile: float = 85.0,
        similarity_threshold: Optional[float] = None,
        min_chunk_size: int = 200,
        max_chunk_size: int = 1500,
    ):
        self.embeddings = embeddings
        self.breakpoint_percentile = breakpoint_percentile
        self.similarity_threshold = similarity_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.classifications_embeddings = None

    def _split_into_sentences(self, text: str) -> List[str]:
        # A list of common abbreviations we don't want to split at
        abbreviations = {'inc', 'corp', 'co', 'ltd', 'pvt', 'e.g', 'i.e', 'vs', 'mr', 'mrs', 'ms', 'dr', 'prof'}
        # Simple regex splitting on punctuation followed by spaces/newlines
        raw_splits = re.split(r'(\.|\?|\!)\s+', text)
        sentences = []
        
        current = ""
        for i in range(0, len(raw_splits), 2):
            part = raw_splits[i].strip()
            if not part:
                continue
            
            punc = raw_splits[i+1] if i+1 < len(raw_splits) else ""
            
            # Check if the sentence candidate ends with a known abbreviation before the period
            words = part.split()
            last_word = words[-1].lower().rstrip('.') if words else ""
            
            if last_word in abbreviations and punc == '.':
                current += part + punc + " "
            else:
                sentences.append((current + part + punc).strip())
                current = ""
                
        if current:
            sentences.append(current.strip())
            
        return [s for s in sentences if s]

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        dot_product = sum(x * y for x, y in zip(v1, v2))
        norm_v1 = math.sqrt(sum(x * x for x in v1))
        norm_v2 = math.sqrt(sum(x * x for x in v2))
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)

    def _percentile(self, data: List[float], percent: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (percent / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_data[int(k)]
        d0 = sorted_data[int(f)] * (c - k)
        d1 = sorted_data[int(c)] * (k - f)
        return d0 + d1

    def _precompute_classification_embeddings(self):
        if self.classifications_embeddings is not None:
            return
        
        print("Precomputing embeddings for VSME classifications...")
        codes = list(VSME_CLASSIFICATIONS.keys())
        descriptions = [VSME_CLASSIFICATIONS[c] for c in codes]
        
        try:
            embs = self.embeddings.embed_documents(descriptions)
            self.classifications_embeddings = {code: emb for code, emb in zip(codes, embs)}
        except Exception as e:
            print(f"Error precomputing VSME classifications: {str(e)}")
            self.classifications_embeddings = {code: [] for code in codes}

    def split_documents(self, documents: List[Document]) -> List[Document]:
        self._precompute_classification_embeddings()
        
        chunked_documents = []
        
        for doc in documents:
            text = doc.page_content
            sentences = self._split_into_sentences(text)
            
            if not sentences:
                continue
                
            if len(sentences) == 1:
                try:
                    chunk_emb = self.embeddings.embed_query(sentences[0])
                    chunk_doc = self._create_chunk_doc_with_embedding(sentences[0], chunk_emb, doc.metadata)
                except Exception:
                    chunk_doc = self._create_chunk_doc_with_embedding(sentences[0], [], doc.metadata)
                chunked_documents.append(chunk_doc)
                continue

            # Embed all sentences in batch
            try:
                sentence_embeddings = self.embeddings.embed_documents(sentences)
            except Exception as e:
                print(f"Error embedding sentences: {str(e)}. Falling back to character-based chunking.")
                try:
                    chunk_emb = self.embeddings.embed_query(text)
                    chunk_doc = self._create_chunk_doc_with_embedding(text, chunk_emb, doc.metadata)
                except Exception:
                    chunk_doc = self._create_chunk_doc_with_embedding(text, [], doc.metadata)
                chunked_documents.append(chunk_doc)
                continue

            # Compute similarities and distances between consecutive sentences
            similarities = []
            for i in range(len(sentences) - 1):
                sim = self._cosine_similarity(sentence_embeddings[i], sentence_embeddings[i+1])
                similarities.append(sim)

            distances = [1.0 - sim for sim in similarities]
            
            # Determine threshold distance for splitting
            if self.similarity_threshold is not None:
                threshold_distance = 1.0 - self.similarity_threshold
            else:
                threshold_distance = self._percentile(distances, self.breakpoint_percentile)

            # Perform grouping
            chunks_texts = []
            current_chunk = []
            current_chunk_len = 0
            
            for i in range(len(sentences)):
                current_chunk.append(sentences[i])
                current_chunk_len += len(sentences[i])
                
                if i < len(sentences) - 1:
                    dist = distances[i]
                    should_split = False
                    
                    # Split if distance exceeds the threshold and we met min size
                    if dist >= threshold_distance and current_chunk_len >= self.min_chunk_size:
                        should_split = True
                    # Force split if the chunk gets too large
                    if current_chunk_len >= self.max_chunk_size:
                        should_split = True
                        
                    if should_split:
                        chunks_texts.append(" ".join(current_chunk))
                        current_chunk = []
                        current_chunk_len = 0
                        
            if current_chunk:
                chunks_texts.append(" ".join(current_chunk))
            
            # Batch embed all generated chunks
            valid_chunks = [ct for ct in chunks_texts if ct.strip()]
            if not valid_chunks:
                continue
                
            try:
                chunk_embeddings = self.embeddings.embed_documents(valid_chunks)
            except Exception as e:
                print(f"Error embedding chunks: {str(e)}")
                chunk_embeddings = [[] for _ in valid_chunks]
                
            # Create LangChain Document objects and classify them using the precomputed batch embeddings
            for chunk_text, chunk_emb in zip(valid_chunks, chunk_embeddings):
                chunk_doc = self._create_chunk_doc_with_embedding(chunk_text, chunk_emb, doc.metadata)
                chunked_documents.append(chunk_doc)
                
        return chunked_documents

    def _create_chunk_doc_with_embedding(self, chunk_text: str, chunk_emb: List[float], original_metadata: Dict[str, Any]) -> Document:
        best_code = "UNKNOWN"
        best_name = "Unknown Classification"
        max_sim = 0.0
        
        if chunk_emb and self.classifications_embeddings:
            for code, emb in self.classifications_embeddings.items():
                if not emb:
                    continue
                sim = self._cosine_similarity(chunk_emb, emb)
                if sim > max_sim:
                    max_sim = sim
                    best_code = code
                    best_name = VSME_CLASSIFICATIONS[code]
            
        metadata = dict(original_metadata)
        metadata.update({
            "vsme_classification_code": best_code,
            "vsme_classification_name": best_name,
            "classification_confidence": max_sim
        })
        
        return Document(page_content=chunk_text, metadata=metadata)
