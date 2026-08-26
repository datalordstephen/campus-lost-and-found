"""TF-IDF keyword baseline.

The comparison this project has to make is not "CLIP vs nothing" but "CLIP vs
what a lost-and-found system would otherwise do", which is keyword search over
whatever text the finder typed when handing the item in.

So the baseline matches the lost report against the *finder's own description*
of the same object — a second, independent human caption. CLIP never sees that
text; it works from the photograph alone. Both methods are given the evidence
their approach would actually have.
"""

from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


def score_matrix(queries: list[str], listings: list[str]) -> np.ndarray:
    """(n_queries, n_listings) cosine similarity over TF-IDF vectors."""
    # Fit on the corpus both sides are drawn from, so the IDF weights are shared.
    vectoriser = TfidfVectorizer(
        stop_words="english",
        sublinear_tf=True,
        ngram_range=(1, 2),
        min_df=1,
    )
    vectoriser.fit(list(listings) + list(queries))

    q = vectoriser.transform(queries)
    d = vectoriser.transform(listings)
    # TfidfVectorizer L2-normalises rows, so the dot product is the cosine.
    return (q @ d.T).toarray()
