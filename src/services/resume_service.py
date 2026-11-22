"""
Resume text extraction and LLM summarisation.

No Streamlit dependency.  Progress goes through the *on_progress* callback.
"""

import re
import mimetypes
from typing import Callable, Optional
from io import BytesIO

import magic
import pytesseract
import html2text
import pdfplumber
from docx import Document
from PIL import Image

import config
from models_sql import Session, Profile
from services.ai_provider import invoke_chat_model

_noop: Callable[[str], None] = lambda msg: None

SUMMARIZATION_RESUME_PROMPT = """\
You are an expert career assistant and AI resume analyst.

Your task is to extract structured, high-quality information from a technical resume to support job matching, scoring, and recommendation.

The goal is to understand the candidate's background, expertise, and value proposition. Focus on highlighting work that demonstrates strong technical depth, real-world impact, and alignment with roles in software engineering, systems engineering, embedded systems, or networking.

Given the following resume text, extract and summarize the most relevant and important information into the following structured categories:

1. **Professional Summary**:
   - Write a concise 2-4 sentence paragraph summarizing the candidate's career highlights, strengths, and technical focus areas.

2. **Top Skills and Technologies**:
   - Extract a bullet-point list of programming languages, tools, platforms, protocols, and technologies mentioned or clearly implied.
   - Group or tag them where relevant (e.g., Programming Languages, Databases, DevOps, etc.).

3. **Key Areas of Expertise**:
   - List 4-8 high-level domains or themes such as embedded systems, CI/CD, simulation, automation, network protocols, telemetry, etc.

4. **Work Experience Highlights**:
   For each relevant role:
   - Company
   - Title
   - Duration (start and end dates or years)
   - Bullet points describing the most impactful contributions (focus on scale, innovation, and technologies used)

5. **Education**:
   - Degree
   - Field of study
   - University name
   - Dates attended (or graduation year)

6. **Publications and Research (if applicable)**:
   - List up to 5 notable publications, conference papers, or research contributions.
   - Include titles and venue if available.

7. **Notable Projects or Open Source Contributions**:
   - List named projects with a short description and technologies involved.
   - Prioritize innovation, scale, and real-world utility.

8. **Other Relevant Attributes** (if any):
   - Teaching, leadership, awards, international experience, or lab/testbed work.

Return your response in well-formatted **Markdown** for readability and optionally include a structured **JSON block** for programmatic access if requested.

Resume:
\"\"\"
[Insert resume text here]
\"\"\"
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_resume(
    profile_name: str,
    on_progress: Callable[[str], None] = _noop,
) -> tuple[bool, Optional[str]]:
    """
    Extract text from a profile's uploaded resume and generate an LLM summary.

    Returns *(True, None)* on success or *(False, error_msg)* on failure.
    """
    if not profile_name:
        return False, "No profile selected"

    with Session() as db_session:
        profile = db_session.query(Profile).filter(Profile.name == profile_name).first()
        if not profile:
            return False, "Profile not found"

        on_progress("Extracting text from the resume...")

        status, output = extract_resume_text(db_session, profile)
        if not status:
            return False, output

        resume_text = output

        on_progress("Summarizing resume...")

        summarization_prompt = SUMMARIZATION_RESUME_PROMPT + "\n\n" + resume_text

        status, output = invoke_chat_model(
            config.llm_model_summarization,
            "You are an expert career assistant and AI resume analyst.",
            summarization_prompt,
        )

        if not status:
            return False, output

        profile.resume_summary = output
        db_session.commit()

        on_progress("Resume preparation complete")

    return True, None


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def extract_resume_text(db_session, profile) -> tuple[bool, str]:
    """Extract plain text from the binary resume stored on *profile*."""
    resume_filename = profile.resume_filename
    resume_bytes = profile.resume_binary

    if not resume_filename or not resume_bytes:
        return False, "resume data is not available"

    effective_mime = get_mime_type(resume_filename, resume_bytes)
    resume_text = extract_text(effective_mime, resume_bytes)

    try:
        profile.resume_text = resume_text
        db_session.commit()
        return True, resume_text
    except Exception as e:
        db_session.rollback()
        return False, f"Failed to save resume text: {e}"


def get_mime_type(filename: str, binary_data: bytes) -> str:
    try:
        detected_type = magic.from_buffer(binary_data, mime=True)
        if detected_type:
            return detected_type
    except Exception:
        pass

    guessed_type, _ = mimetypes.guess_type(filename)
    if guessed_type:
        return guessed_type

    return "application/octet-stream"


def extract_text(effective_mime: str, binary_data: bytes) -> str:
    text_data = ""

    if effective_mime in ["text/plain"]:
        try:
            text_data = binary_data.decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"Error: extract_text: {e}")

    elif effective_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            doc = Document(BytesIO(binary_data))
            text_data = "\n".join(para.text for para in doc.paragraphs)
        except Exception as e:
            print(f"Error: extract_text: {e}")

    elif effective_mime == "application/pdf":
        try:
            with pdfplumber.open(BytesIO(binary_data)) as pdf:
                all_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            text_data = all_text.strip()
        except Exception as e:
            print(f"Error: extract_text: {e}")

    elif effective_mime == "text/html":
        try:
            html_txt = binary_data.decode("utf-8", errors="ignore")
            status, output = _html_to_text(html_txt)
            if status and output:
                text_data = output
        except Exception as e:
            print(f"Error: extract_text: {e}")

    elif effective_mime in ["image/jpeg", "image/png"]:
        try:
            image = Image.open(BytesIO(binary_data))
            text = pytesseract.image_to_string(image)
            text_data = text.strip()
        except Exception as e:
            print(f"Error: extract_text: {e}")
    else:
        print(f"Warning: unsupported MIME type: {effective_mime}")

    return text_data.replace("\x00", "")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _html_to_text(html_text: str) -> tuple[bool, str]:
    try:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.body_width = 0
        h.ignore_emphasis = True
        h.skip_internal_links = True
        h.ignore_tables = True
        h.protect_links = True

        text = h.handle(html_text)
        text = re.sub(r"[\u200c\u200d\u200e\u200f\u202a-\u202e\u2060-\u206f\u00ad\xa0]", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)

        return True, text.strip()
    except Exception as e:
        return False, f"Error in parsing html: {str(e)}"
