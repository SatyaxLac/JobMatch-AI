"""
LLM chat / RAG Q&A over selected job chunks in PostgreSQL pgvector.

No Streamlit dependency.  Progress goes through the *on_progress* callback.
"""

from typing import Callable, Optional

import config
from models_sql import Session, Profile
from services.ai_provider import invoke_chat_model
from services.embedding_utils import get_embedding_model
from services.retrieval_service import PgVectorJobRetriever

_noop: Callable[[str], None] = lambda msg: None

INSTRUCTIONS = """\
You are a professional Job Advisor assisting users in evaluating job opportunities.
You will be given context documents (retrieved job descriptions, highlights, company details, etc.) along with a user's question or preference.
Use only the provided context to guide your response - do not make up details that are not explicitly mentioned.

Your goal is to help the user make an informed career decision. Specifically:
- Understand the user's priorities (e.g., remote work, salary, benefits, skills match, company size).
- Extract and compare relevant information from the job postings.
- Explain trade-offs clearly (e.g., stability vs. growth, salary vs. flexibility).
- Recommend the most suitable job based on the user's stated goals.

Be concise, objective, and user-centric.
If the context is insufficient, tell the user what information is missing.
"""

INSTRUCTIONS_RESUME = """\
The user's resume is provided at the end of the context.
Use it to assess how well each job matches the user's background, skills, and experience.
Consider resume-job alignment when scoring or recommending jobs.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_prompt_to_llm(
    user_prompt: str,
    job_ids_to_process: list[str],
    resume_summary: Optional[str] = None,
    on_progress: Callable[[str], None] = _noop,
) -> tuple[bool, str]:
    """
    Retrieve relevant job chunks from pgvector and call the chat model directly.

    Returns *(True, answer_text)* on success or *(False, error_msg)* on failure.
    """
    if not job_ids_to_process:
        return False, "No jobs were provided for retrieval"

    # Build instructions — fresh copy each call (no global mutation)
    instructions = INSTRUCTIONS
    if resume_summary:
        instructions += INSTRUCTIONS_RESUME + "\n\n" + resume_summary

    on_progress("Loading local embedding model...")
    try:
        retriever = PgVectorJobRetriever(
            job_ids=job_ids_to_process,
            embeddings=get_embedding_model(),
            top_k=10,
            min_similarity=0.7,
        )
        on_progress(f"Retrieving relevant chunks from {len(job_ids_to_process)} jobs...")
        documents = retriever.invoke(user_prompt)

        context = "\n\n---\n\n".join(
            "Job: {title} | Company: {company} | Job ID: {job_id}\n{content}".format(
                title=document.metadata.get("title", "Unknown"),
                company=document.metadata.get("company", "Unknown"),
                job_id=document.metadata.get("job_id", "Unknown"),
                content=document.page_content,
            )
            for document in documents
        )

        on_progress(f"Generating a response with {config.llm_model_chat}...")
        direct_prompt = (
            "Use the following retrieved job context to answer the question. "
            "If it does not contain enough information, say so.\n\n"
            f"Retrieved jobs:\n{context}\n\nQuestion:\n{user_prompt}"
        )
        status, answer = invoke_chat_model(
            config.llm_model_chat,
            instructions,
            direct_prompt,
        )
        if not status:
            return False, answer
    except Exception as exc:
        return False, f"Failed to retrieve jobs or call the language model: {exc}"
    return True, answer


def get_resume_summary(profile_name: str) -> Optional[str]:
    """Return the LLM-generated resume summary for the given profile, or *None*."""
    if not profile_name:
        return None
    with Session() as db_session:
        profile = db_session.query(Profile).filter(Profile.name == profile_name).first()
        if profile and profile.resume_summary:
            return profile.resume_summary
    return None


def get_resume_text(profile_name: str) -> Optional[str]:
    """Return the extracted plain-text resume for the given profile, or *None*."""
    if not profile_name:
        return None
    with Session() as db_session:
        profile = db_session.query(Profile).filter(Profile.name == profile_name).first()
        if profile and profile.resume_text:
            return profile.resume_text
    return None
