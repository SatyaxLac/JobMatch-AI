"""Direct LangChain chat-model calls used by the service layer."""

from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


@lru_cache(maxsize=4)
def _get_chat_model(model_name: str) -> ChatOpenAI:
    return ChatOpenAI(model=model_name, use_responses_api=True)


def invoke_chat_model(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[bool, str]:
    """Invoke OpenAI directly through LangChain and return text or an error."""
    try:
        response = _get_chat_model(model_name).invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
    except Exception as exc:
        return False, str(exc)

    content = response.content
    if isinstance(content, str):
        return True, content

    if isinstance(content, list):
        text_parts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        if text_parts:
            return True, "\n".join(text_parts)

    return True, str(content)
