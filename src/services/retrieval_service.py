"""LangChain retriever backed by the job_embeddings pgvector table."""

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from models_sql import Job, JobEmbedding, Session


class PgVectorJobRetriever(BaseRetriever):
    """Retrieve nearest job chunks from PostgreSQL for a selected job set."""

    job_ids: list[str]
    embeddings: Any
    top_k: int = 10
    min_similarity: float = 0.7

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        if not self.job_ids:
            return []

        query_vector = self.embeddings.embed_query(query)
        cosine_distance = JobEmbedding.embedding.cosine_distance(query_vector)
        max_distance = 1.0 - self.min_similarity

        with Session() as db_session:
            rows = (
                db_session.query(Job, JobEmbedding, cosine_distance.label("distance"))
                .join(JobEmbedding, JobEmbedding.job_id == Job.id)
                .filter(Job.job_id.in_(self.job_ids))
                .filter(cosine_distance <= max_distance)
                .order_by(cosine_distance)
                .limit(self.top_k)
                .all()
            )

            return [
                Document(
                    page_content=embedding.chunk_text,
                    metadata={
                        "job_id": job.job_id,
                        "title": job.title,
                        "company": job.company.name if job.company else "Unknown",
                    },
                )
                for job, embedding, _distance in rows
            ]
