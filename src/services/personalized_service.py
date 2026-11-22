"""
Personalised resume and cover-letter generation.

No Streamlit dependency.  Progress goes through the *on_progress* callback.
"""

from typing import Callable, Optional

import config
from models_sql import Session, Job
from services.ai_provider import invoke_chat_model
from services.enrichment_service import summarize_jobs

_noop: Callable[[str], None] = lambda msg: None

PROMPT_RESUME = """\
You are an expert resume coach and writer.

I'm providing two inputs:

1. My current resume (below)
2. A job description for a role I want to apply to (below)

Your task is to:
- Review my resume and suggest improvements to make it sharper, more results-driven, and aligned with modern hiring standards.
- Identify mismatches or gaps between my resume and the job description.
- Rewrite the resume fully to:
    - Use language, tone, and priorities aligned with the job description
    - Emphasize relevant skills, experiences, and keywords
    - Highlight specific achievements and measurable impact

The final version should be professional, focused, and customized for this role.

---
My Resume:
{MY_RESUME_HERE}

---
Job Description:
{JOB_DESCRIPTION_HERE}
"""

PROMPT_COVER_LETTER = """\
You are a professional cover letter writer.

Using the resume and job description below, write a customized, confident, and persuasive cover letter for this role.

The cover letter should:
- Reflect the key highlights of my resume (without repeating it word-for-word)
- Speak directly to the job's responsibilities and requirements
- Convey personality, enthusiasm, and motivation for the role
- Have a professional but personable tone
- Be no longer than one **A4 page** (typically 4 paragraphs)

Avoid generic filler and focus on why I'm a strong match for this specific position.

---
My Resume:
{MY_RESUME_HERE}

---
Job Description:
{JOB_DESCRIPTION_HERE}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_resume_and_cover_letter(
    job_id: int,
    resume_text: str,
    on_progress: Callable[[str], None] = _noop,
) -> tuple[bool, dict | str]:
    """
    Generate a tailored resume and cover letter for *job*.

    Returns *(True, {"resume": ..., "cover_letter": ...})* on success
    or *(False, error_msg)* on failure.
    """
    if not resume_text:
        return False, "No resume found"

    with Session() as db_session:
        job = db_session.get(Job, job_id)
        if not job:
            return False, "Job not found"

        # Ensure the job has a summary -------------------------------------
        if not job.job_summary:
            status, output = summarize_jobs(db_session, [job], on_progress)
            if not status:
                return False, output
        job_summary = job.job_summary

    # Generate tailored resume ---------------------------------------------
    on_progress("Generating updated resume...")

    question = PROMPT_RESUME.format(
        MY_RESUME_HERE=resume_text,
        JOB_DESCRIPTION_HERE=job_summary,
    )

    status, resume_output = invoke_chat_model(
        config.llm_model_chat,
        "You are an expert resume coach and writer.",
        question,
    )

    if not status:
        return False, f"resume generation failed: {resume_output}"

    # Generate cover letter -------------------------------------------------
    on_progress("Generating cover letter...")

    question = PROMPT_COVER_LETTER.format(
        MY_RESUME_HERE=resume_text,
        JOB_DESCRIPTION_HERE=job_summary,
    )

    status, cover_output = invoke_chat_model(
        config.llm_model_chat,
        "You are a professional cover letter writer.",
        question,
    )

    if not status:
        return False, f"cover letter generation failed: {cover_output}"

    return True, {
        "resume": resume_output,
        "cover_letter": cover_output,
    }
