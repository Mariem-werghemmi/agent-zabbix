import logging
from openai import OpenAI
from config import settings

logger = logging.getLogger(__name__)
_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout,
        )
        logger.info(
            "Client LLM initialise : modele=%s endpoint=%s",
            settings.llm_model,
            settings.llm_base_url,
        )
    return _client


def chat(messages: list, tools: list | None = None):
    client = get_client()
    kwargs = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message


def check_connection() -> dict:
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "Reponds uniquement : OK"}],
            max_tokens=10,
            temperature=0,
        )
        return {
            "ok": True,
            "model": settings.llm_model,
            "endpoint": settings.llm_base_url,
            "reponse": response.choices[0].message.content,
        }
    except Exception as exc:
        return {
            "ok": False,
            "model": settings.llm_model,
            "endpoint": settings.llm_base_url,
            "error": str(exc),
        }
