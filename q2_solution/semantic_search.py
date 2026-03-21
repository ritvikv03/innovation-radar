"""
Semantic Search Module for Fendt PESTEL-EL Sentinel
====================================================

Provides local vector-based semantic search over the signal corpus.
Uses TF-IDF embeddings with cosine similarity (scikit-learn).
Falls back to keyword matching if sklearn is unavailable.

No external API calls — runs entirely locally.
"""

from typing import List, Dict, Tuple, Optional


class SemanticSearch:
    """
    Local TF-IDF based semantic search over the signal corpus.

    Primary: sklearn TfidfVectorizer + cosine_similarity
    Fallback: Simple keyword matching (pure Python, no deps)
    """

    def __init__(self):
        self._vectorizer = None
        self._matrix = None
        self._signals: List[Dict] = []
        self._sklearn_available = False

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401
            from sklearn.metrics.pairwise import cosine_similarity        # noqa: F401
            self._sklearn_available = True
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def build_index(self, signals: List[Dict]) -> None:
        """
        Build the TF-IDF search index from a list of signal dicts.
        Each signal should have 'title', 'content', and optionally 'source'.
        """
        self._signals = signals
        if not signals:
            return

        if self._sklearn_available:
            from sklearn.feature_extraction.text import TfidfVectorizer

            corpus = [self._signal_to_text(s) for s in signals]
            self._vectorizer = TfidfVectorizer(
                max_features=8000,
                stop_words='english',
                ngram_range=(1, 2),
                sublinear_tf=True,
            )
            self._matrix = self._vectorizer.fit_transform(corpus)

    def _signal_to_text(self, sig: Dict) -> str:
        parts = [
            sig.get('title', ''),
            sig.get('content', ''),
            sig.get('source', ''),
            sig.get('primary_dimension', ''),
        ]
        return ' '.join(p for p in parts if p).lower()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10, min_score: float = 0.01) -> List[Tuple[Dict, float]]:
        """
        Find the top_k signals most semantically similar to query.

        Returns:
            List of (signal_dict, score) tuples, sorted by relevance descending.
        """
        if not self._signals:
            return []

        if self._sklearn_available and self._matrix is not None:
            return self._tfidf_search(query, top_k, min_score)
        else:
            return self._keyword_search(query, top_k)

    def _tfidf_search(self, query: str, top_k: int, min_score: float) -> List[Tuple[Dict, float]]:
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        query_vec = self._vectorizer.transform([query.lower()])
        scores = cosine_similarity(query_vec, self._matrix)[0]

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = [
            (self._signals[i], float(scores[i]))
            for i in top_indices
            if float(scores[i]) >= min_score
        ]
        return results

    def _keyword_search(self, query: str, top_k: int) -> List[Tuple[Dict, float]]:
        """Simple term-overlap fallback."""
        query_terms = [t for t in query.lower().split() if len(t) > 2]
        if not query_terms:
            return []

        results = []
        for sig in self._signals:
            text = self._signal_to_text(sig)
            matches = sum(1 for term in query_terms if term in text)
            if matches > 0:
                score = matches / len(query_terms)
                results.append((sig, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def filter_by_keywords(self, keywords: List[str], signals: Optional[List[Dict]] = None) -> List[Dict]:
        """
        Return signals (from index or provided list) containing ANY keyword.
        Case-insensitive substring match.
        """
        source = signals if signals is not None else self._signals
        matching = []
        kw_lower = [k.lower() for k in keywords]
        for sig in source:
            text = self._signal_to_text(sig)
            if any(kw in text for kw in kw_lower):
                matching.append(sig)
        return matching

    def is_sklearn_available(self) -> bool:
        return self._sklearn_available

    def index_size(self) -> int:
        return len(self._signals)
