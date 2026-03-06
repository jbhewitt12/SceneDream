# openai_api.py
# This module provides a set of wrapper functions for making various calls to OpenAI's LLM
# using the LangChain library. It supports simple text generation, chat-style interactions,
# tool/function calling, structured output using Pydantic schemas, and JSON-formatted output.
# The functions are designed to be easy to use, with defaults for common parameters.
# Assumptions:
# - The OPENAI_API_KEY is stored in a .env file in the project root.
# - The langchain-openai package is installed (pip install langchain-openai).
# - For tool calling and structured output, use models that support these features (e.g., gpt-4o or gpt-4o-mini).
# - All functions handle API key loading internally via dotenv.
# - Error handling is minimal; add try-except blocks as needed in production.
# - Comments are provided for each function to explain usage, parameters, and return values,
#   so a coding agent can easily understand and extend the code.
# - Methods have been converted to asynchronous versions for concurrency in environments like FastAPI.
# - Assumes latest LangChain where async support for ChatOpenAI is functional.

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

DEFAULT_FLASH_MODEL = "gpt-4o-mini"
DEFAULT_PRO_MODEL = "gpt-4o"

logger = logging.getLogger(__name__)


async def retry_with_backoff(async_func: Any, *args: Any, **kwargs: Any) -> Any:
    """
    Clauses asynchronous retry wrapper with exponential backoff.
    Retries the async function on exceptions.
    """
    retrying = AsyncRetrying(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            return await async_func(*args, **kwargs)


def _coerce_content_to_text(payload: Any) -> str:
    """Normalize OpenAI message content into a plain string."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        # Handle rare multimodal content parts
        parts = [
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in payload
        ]
        return "".join(parts)
    return str(payload)


def _get_llm(
    model: str = DEFAULT_FLASH_MODEL,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """
    Internal helper function to initialize the ChatOpenAI LLM.
    Loads the API key from .env and configures the model with provided parameters.

    :param model: The OpenAI model name (e.g., "gpt-4o", "gpt-4o-mini").
    :param temperature: Controls randomness (0.0 for deterministic, higher for creative).
    :param max_tokens: Maximum number of tokens in the response (optional).
    :param response_format: Optional response format (e.g., {"type": "json_object"}).
    :param kwargs: Additional parameters like timeout, max_retries, etc.
    :return: Initialized ChatOpenAI instance.
    """
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in .env file.")

    return ChatOpenAI(  # type: ignore[call-arg]
        model=model,
        openai_api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        **kwargs,
    )


async def simple_call(
    prompt: str,
    model: str = DEFAULT_FLASH_MODEL,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> str:
    """
    Makes a simple LLM call with a single prompt string.
    Useful for basic text generation or completion tasks.

    Example usage:
    response = await simple_call("Write a short poem about AI.")
    print(response)

    :param prompt: The input prompt string.
    :param model: The OpenAI model to use.
    :param temperature: Randomness control.
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: The generated text response as a string.
    """
    kwargs.setdefault("request_timeout", 120)
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    response = await retry_with_backoff(llm.ainvoke, prompt)
    return _coerce_content_to_text(response.content)


async def chat_call(
    messages: list[dict[str, str]],
    model: str = DEFAULT_FLASH_MODEL,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> str:
    """
    Makes a chat-style LLM call with a list of messages (supports system, user, assistant roles).
    Converts input dicts to LangChain message objects.

    Example usage:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"}
    ]
    response = await chat_call(messages)
    print(response)

    :param messages: List of dicts with 'role' (system/user/assistant) and 'content'.
    :param model: The OpenAI model to use.
    :param temperature: Randomness control.
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: The generated response as a string.
    """
    kwargs.setdefault("request_timeout", 120)
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = []
    for msg in messages:
        role = msg.get("role", "").lower()
        content = msg.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            raise ValueError(f"Unsupported role: {role}")

    response = await retry_with_backoff(llm.ainvoke, lc_messages)
    return _coerce_content_to_text(response.content)


async def call_with_tools(
    prompt: str,
    tools: list[Any],
    model: str = DEFAULT_PRO_MODEL,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> Any:
    """
    Makes an LLM call with bound tools/functions for function calling.
    The LLM may return tool calls in the response if the prompt requires it.
    Tools can be defined using @tool decorator or as dicts.

    Example usage:
    @tool
    def add(a: int, b: int) -> int:
        return a + b

    response = await call_with_tools("What is 2 + 3?", tools=[add])
    if response.tool_calls:
        # Handle tool execution here
        pass

    :param prompt: The input prompt string.
    :param tools: List of tools (functions or dict schemas).
    :param model: The OpenAI model to use (must support tool calling).
    :param temperature: Randomness control.
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: The full AIMessage response (may include .tool_calls list).
    """
    kwargs.setdefault("request_timeout", 180)
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    llm_with_tools = llm.bind_tools(tools)
    response = await retry_with_backoff(llm_with_tools.ainvoke, prompt)
    return response


async def structured_output(
    prompt: str,
    schema: type[BaseModel],
    method: str = "default",
    model: str = DEFAULT_PRO_MODEL,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> BaseModel:
    """
    Makes an LLM call that enforces structured output based on a Pydantic schema.
    Useful for extracting data in a specific format.

    Example usage:
    class Person(BaseModel):
        name: str
        age: int

    result = await structured_output("Extract info: John is 30 years old.", Person)
    print(result.name, result.age)

    :param prompt: The input prompt string.
    :param schema: Pydantic BaseModel subclass defining the structure.
    :param method: "default" (function calling) or "json_mode" (native JSON).
    :param model: The OpenAI model to use.
    :param temperature: Randomness control (low for structured output).
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: Instance of the schema with parsed data.
    """
    kwargs.setdefault("request_timeout", 240)
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    structured_llm = llm.with_structured_output(
        schema,
        method="json_mode" if method == "json_mode" else "function_calling",
    )

    result = await retry_with_backoff(structured_llm.ainvoke, prompt)
    if not isinstance(result, BaseModel):
        raise ValueError(f"Expected BaseModel result, got {type(result)}")
    return result


async def json_output(
    prompt: str,
    system_instruction: str = "Respond only with valid JSON.",
    model: str = DEFAULT_PRO_MODEL,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    force_json_object: bool = True,
    **kwargs: Any,
) -> Any:
    """
    Makes an LLM call that forces JSON output using response_format.
    Parses the response to a Python dict.

    Example usage:
    response = await json_output("List 3 fruits as JSON array.")
    print(response)  # e.g., {"fruits": ["apple", "banana", "cherry"]}

    :param prompt: The input prompt string.
    :param system_instruction: System prompt to enforce JSON (optional).
    :param model: The OpenAI model to use.
    :param temperature: Randomness control (low for JSON).
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :param force_json_object: Enforce a top-level JSON object via OpenAI response_format.
    :return: Parsed JSON payload.
    """
    response_format = {"type": "json_object"} if force_json_object else None
    kwargs.setdefault("request_timeout", 360)
    llm = _get_llm(
        model,
        temperature,
        max_tokens,
        response_format=response_format,
        **kwargs,
    )
    messages = [SystemMessage(content=system_instruction), HumanMessage(content=prompt)]
    response = await retry_with_backoff(llm.ainvoke, messages)
    content = _coerce_content_to_text(response.content).strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() in {"```", "```json"}:
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        metadata = getattr(response, "response_metadata", {}) or {}
        finish_reason = metadata.get("finish_reason")
        snippet = content[:500]
        logger.debug(
            "OpenAI JSON decode failed. finish_reason=%s snippet=%r",
            finish_reason,
            snippet,
        )
        if finish_reason == "length":
            raise ValueError(
                "OpenAI response truncated before completing JSON (finish_reason=length). "
                "Increase max_tokens or adjust the prompt for shorter output."
            ) from exc
        raise ValueError("Failed to parse JSON from response: " + snippet) from exc
