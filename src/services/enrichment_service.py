"""
Job summarisation and local pgvector indexing.

No Streamlit dependency.  Progress goes through the *on_progress* callback.
"""

from functools import lru_cache
from typing import Callable, Optional

from sqlalchemy import delete
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

import config
from models_sql import Session, Job, JobEmbedding
from services.ai_provider import invoke_chat_model
from services.embedding_utils import get_embedding_model

_noop: Callable[[str], None] = lambda msg: None

SUMMARIZATION_JOB_PROMPT = """\
You are an intelligent and helpful career assistant trained to extract key insights from job postings to help candidates quickly assess fit and interest.

Given the following job posting, extract and summarize the following structured information:

1. **Role Overview** - What are the primary responsibilities and objectives of the position?
2. **Experience Level** - Determine whether the role is Intern, Entry-Level, Junior, Mid-Level, Senior, Lead / Staff, Principal / Architect or Executive.
3. **Required Skills & Technologies** - List **all technologies**, tools, programming languages, and frameworks mentioned (including scripting or backend tools).
4. **Preferred Experience or Qualifications** - Summarize any additional desirable qualifications.
5. **Company or Role Highlights** - Mention any unique benefits, perks, or noteworthy aspects of the company or role.

**Instructions**:
- Be concise and use bullet points where appropriate.
- Use professional language suitable for job seekers comparing roles.
- Ensure accuracy and do not assume unlisted technologies or details.

Here is the job text:
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_and_embed(
    job_ids_to_process: list[str],
    on_progress: Callable[[str], None] = _noop,
) -> tuple[bool, Optional[str]]:
    """Summarise jobs and persist local embeddings to PostgreSQL pgvector."""
    if not job_ids_to_process:
        return True, None

    db_session = Session()
    try:
        return _summarize_and_embed_jobs(db_session, job_ids_to_process, on_progress)
    finally:
        db_session.close()


def summarize_jobs(
    db_session,
    jobs_not_summarized,
    on_progress: Callable[[str], None] = _noop,
) -> tuple[bool, Optional[str]]:
    """Summarise a list of Job objects via LLM.  Public — also used by
    personalized_service."""
    on_progress(f"Summarizing {len(jobs_not_summarized)} jobs with {config.llm_model_summarization}...")

    for index, job in enumerate(jobs_not_summarized, start=1):
        job_text = _extract_job(job)
        if len(job_text) > config.summarization_max_characters:
            on_progress(
                f"Job text for {job.job_id} exceeds the summarization limit; truncating."
            )
            job_text = job_text[:config.summarization_max_characters]

        status, final_summary = invoke_chat_model(
            config.llm_model_summarization,
            SUMMARIZATION_JOB_PROMPT,
            job_text,
        )

        if not status:
            return False, final_summary

        job_header_str = _extract_job(job, include_body=False)
        job.job_summary = job_header_str + "\n\n" + final_summary
        job.is_summarized = True

        db_session.add(job)
        db_session.commit()
        on_progress(f"Summarized job {index} of {len(jobs_not_summarized)}")

    on_progress("Summarization complete")
    return True, None


def clear_summarizations() -> None:
    """Reset the *is_summarized* flag on every job."""
    db_session = Session()
    try:
        db_session.query(Job).filter(Job.is_summarized == True).update(
            {Job.is_summarized: False}, synchronize_session=False,
        )
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise


def clear_embeddings() -> None:
    """Reset the *is_embedded* flag and delete all JobEmbedding rows."""
    db_session = Session()
    try:
        db_session.query(Job).filter(Job.is_embedded == True).update(
            {Job.is_embedded: False}, synchronize_session=False,
        )
        db_session.execute(delete(JobEmbedding))
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _summarize_and_embed_jobs(db_session, job_ids_to_process, on_progress):
    jobs_not_summarized = (
        db_session.query(Job)
        .filter(Job.job_id.in_(job_ids_to_process), Job.is_summarized == False)
        .all()
    )
    if jobs_not_summarized:
        status, output = summarize_jobs(db_session, jobs_not_summarized, on_progress)
        if not status:
            return False, output

    jobs_not_embedded = (
        db_session.query(Job)
        .filter(
            Job.job_id.in_(job_ids_to_process),
            Job.is_summarized == True,
            Job.is_embedded == False,
        )
        .all()
    )
    if jobs_not_embedded:
        status, output = _embed_jobs(db_session, jobs_not_embedded, on_progress)
        if not status:
            return False, output

    return True, None


@lru_cache(maxsize=1)
def _get_embedding_tokenizer():
    """Load the matching tokenizer so splitter limits are measured in tokens."""
    return AutoTokenizer.from_pretrained(config.local_embed_model)


def _embed_jobs(db_session, jobs_not_embedded, on_progress):
    on_progress(f"Loading local embedding model: {config.local_embed_model}...")
    try:
        embeddings = get_embedding_model()
    except Exception as exc:
        return False, f"Could not load embedding model: {exc}"

    try:
        splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            _get_embedding_tokenizer(),
            chunk_size=config.embedding_chunk_size,
            chunk_overlap=config.embedding_chunk_overlap,
        )

        chunks_by_job = []
        all_chunks = []
        for job in jobs_not_embedded:
            chunks = splitter.split_text(job.job_summary or "")
            if not chunks:
                return False, f"Job {job.job_id} has no text to embed"
            chunks_by_job.append((job, chunks))
            all_chunks.extend(chunks)
    except Exception as exc:
        return False, f"Could not split job summaries for embedding: {exc}"

    on_progress(
        f"Embedding {len(all_chunks)} chunks across {len(jobs_not_embedded)} jobs..."
    )
    try:
        vectors = embeddings.embed_documents(all_chunks)
    except Exception as exc:
        return False, f"Embedding error: {exc}"

    if len(vectors) != len(all_chunks):
        return False, "Embedding model returned a different number of vectors than chunks"
    if any(len(vector) != config.embedding_dimensions for vector in vectors):
        return False, (
            f"Embedding model returned vectors with an unexpected dimension; "
            f"expected {config.embedding_dimensions}"
        )

    vector_offset = 0
    try:
        for job_index, (job, chunks) in enumerate(chunks_by_job, start=1):
            db_session.query(JobEmbedding).filter_by(job_id=job.id).delete(
                synchronize_session=False
            )
            job_vectors = vectors[vector_offset:vector_offset + len(chunks)]
            vector_offset += len(chunks)

            db_session.add_all(
                JobEmbedding(
                    job_id=job.id,
                    chunk_index=chunk_index,
                    chunk_text=chunk,
                    embedding=vector,
                )
                for chunk_index, (chunk, vector) in enumerate(zip(chunks, job_vectors))
            )
            job.is_embedded = True
            db_session.add(job)
            db_session.commit()
            on_progress(f"Embedded job {job_index} of {len(chunks_by_job)}")
    except Exception as exc:
        db_session.rollback()
        return False, f"Failed to save embeddings: {exc}"

    on_progress("Embedding done!")
    return True, None


def _extract_job(job, include_header=True, include_body=True, include_highlights=True):
    parts = []
    if include_header:
        parts.extend(_extract_job_header(job))
    if include_body:
        parts.extend(_extract_job_body(job, include_highlights))
    return "\n".join(part for part in parts if part.strip())


def _extract_job_header(job):
    return [
        f"Company: {job.company.name if job.company else 'N/A'}",
        f"Job Location: {job.location or job.city or ''}",
        f"Remote: {'Yes' if job.is_remote else 'No'}",
        f"Employment Type: {', '.join(job.employment_type or [])}",
        f"Job Title: {job.title}",
    ]


def _extract_job_body(job, include_highlights=True):
    parts = [f"Job Description: {job.description or 'N/A'}"]

    if include_highlights and job.job_highlights:
        highlights = "\n".join(
            f"{section}: {', '.join(items)}"
            for section, items in job.job_highlights.items()
            if items
        )
        parts.append(f"Job Highlights:\n{highlights}")

    parts.append(f"Job Benefits: {job.job_benefits or 'N/A'}")
    return parts
