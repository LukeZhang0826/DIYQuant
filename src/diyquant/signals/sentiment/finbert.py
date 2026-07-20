"""FinBERT headline scorer: ProsusAI/finbert, runs locally on CPU.

First use downloads the model (~420 MB) to the Hugging Face cache. The
transformers/torch import is deferred to the constructor so the rest of the
package imports stay fast and tests never need the model.
"""


class FinbertScorer:
    _MODEL = "ProsusAI/finbert"

    def __init__(self):
        from transformers import pipeline

        self._pipe = pipeline("text-classification", model=self._MODEL, top_k=None)

    def score_headlines(self, headlines: list[str]) -> list[float]:
        """Score each headline in [-1, +1] as P(positive) - P(negative)."""
        if not headlines:
            return []
        results = self._pipe(headlines, truncation=True)
        scores = []
        for label_probs in results:
            by_label = {p["label"]: p["score"] for p in label_probs}
            scores.append(by_label.get("positive", 0.0) - by_label.get("negative", 0.0))
        return scores
