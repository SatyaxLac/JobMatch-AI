"""Profile-scoped AI chat over the current job search results."""

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_profile
from api.schemas import ChatRead, ChatRequest
from models_sql import Profile
from services.chat_service import send_prompt_to_llm

router = APIRouter(prefix="/profiles", tags=["chat"])


@router.post("/{profile_name}/chat", response_model=ChatRead)
def chat_with_jobs(
    profile_name: str,
    payload: ChatRequest,
    profile: Profile = Depends(require_profile),
):
    success, answer = send_prompt_to_llm(
        payload.prompt,
        payload.job_ids,
        resume_summary=profile.resume_summary,
    )
    if not success:
        raise HTTPException(status_code=502, detail=answer)
    return ChatRead(answer=answer)
