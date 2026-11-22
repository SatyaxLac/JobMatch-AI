"""Shared local embedding model used for indexing and query retrieval."""

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

import config


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    """Load and reuse BGE-M3 in this app process."""
    return HuggingFaceEmbeddings(
        model_name=config.local_embed_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
        show_progress=False,
    )
