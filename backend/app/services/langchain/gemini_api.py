# gemini_api.py
# This module provides a set of wrapper functions for making various calls to Google's Gemini LLM
# using the LangChain library. It supports simple text generation, chat-style interactions,
# tool/function calling, structured output using Pydantic schemas, and JSON-formatted output.
# The functions are designed to be easy to use, with defaults for common parameters.
# Assumptions:
# - The GEMINI_API_KEY is stored in a .env file in the project root.
# - The langchain-google-genai package is installed (pip install langchain-google-genai).
# - For tool calling and structured output, use models that support these features (e.g., gemini-pro-latest or gemini-flash-latest).
# - All functions handle API key loading internally via dotenv.
# - Error handling is minimal; add try-except blocks as needed in production.
# - Comments are provided for each function to explain usage, parameters, and return values,
#   so a coding agent can easily understand and extend the code.

import logging
import os
from typing import Any, Dict, List, Type

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool  # For defining tools if needed
from pydantic import BaseModel

DEFAULT_FLASH_MODEL = "gemini-flash-latest"
DEFAULT_PRO_MODEL = "gemini-pro-latest"

logger = logging.getLogger(__name__)


def _coerce_content_to_text(payload: Any) -> str:
    """Normalize Gemini message content into a plain string."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts = [str(item) for item in payload if isinstance(item, str)]
        if parts:
            return "".join(parts)
    return str(payload)


def _get_llm(
    model: str = DEFAULT_FLASH_MODEL,
    temperature: float = 0.7,
    max_tokens: int = None,
    **kwargs: Any,
) -> ChatGoogleGenerativeAI:
    """
    Internal helper function to initialize the ChatGoogleGenerativeAI LLM.
    Loads the API key from .env and configures the model with provided parameters.

    :param model: The Gemini model name (e.g., "gemini-pro-latest", "gemini-flash-latest").
    :param temperature: Controls randomness (0.0 for deterministic, higher for creative).
    :param max_tokens: Maximum number of tokens in the response (optional).
    :param kwargs: Additional parameters like timeout, max_retries, etc.
    :return: Initialized ChatGoogleGenerativeAI instance.
    """
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file.")

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def simple_call(
    prompt: str,
    model: str = DEFAULT_FLASH_MODEL,
    temperature: float = 0.7,
    max_tokens: int = None,
    **kwargs: Any,
) -> str:
    """
    Makes a simple LLM call with a single prompt string.
    Useful for basic text generation or completion tasks.

    Example usage:
    response = simple_call("Write a short poem about AI.")
    print(response)

    :param prompt: The input prompt string.
    :param model: The Gemini model to use.
    :param temperature: Randomness control.
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: The generated text response as a string.
    """
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    response = llm.invoke(prompt)
    return response.content


def chat_call(
    messages: List[Dict[str, str]],
    model: str = DEFAULT_FLASH_MODEL,
    temperature: float = 0.7,
    max_tokens: int = None,
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
    response = chat_call(messages)
    print(response)

    :param messages: List of dicts with 'role' (system/user/assistant) and 'content'.
    :param model: The Gemini model to use.
    :param temperature: Randomness control.
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: The generated response as a string.
    """
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    lc_messages = []
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

    response = llm.invoke(lc_messages)
    return response.content


def call_with_tools(
    prompt: str,
    tools: List[Any],
    model: str = DEFAULT_PRO_MODEL,
    temperature: float = 0.7,
    max_tokens: int = None,
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

    response = call_with_tools("What is 2 + 3?", tools=[add])
    if response.tool_calls:
        # Handle tool execution here
        pass

    :param prompt: The input prompt string.
    :param tools: List of tools (functions or dict schemas).
    :param model: The Gemini model to use (must support tool calling).
    :param temperature: Randomness control.
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: The full AIMessage response (may include .tool_calls list).
    """
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    llm_with_tools = llm.bind_tools(tools)
    response = llm_with_tools.invoke(prompt)
    return response


def structured_output(
    prompt: str,
    schema: Type[BaseModel],
    method: str = "default",
    model: str = DEFAULT_PRO_MODEL,
    temperature: float = 0.0,
    max_tokens: int = None,
    **kwargs: Any,
) -> BaseModel:
    """
    Makes an LLM call that enforces structured output based on a Pydantic schema.
    Useful for extracting data in a specific format.

    Example usage:
    class Person(BaseModel):
        name: str
        age: int

    result = structured_output("Extract info: John is 30 years old.", Person)
    print(result.name, result.age)

    :param prompt: The input prompt string.
    :param schema: Pydantic BaseModel subclass defining the structure.
    :param method: "default" (function calling) or "json_mode" (native JSON).
    :param model: The Gemini model to use.
    :param temperature: Randomness control (low for structured output).
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: Instance of the schema with parsed data.
    """
    llm = _get_llm(model, temperature, max_tokens, **kwargs)
    if method == "json_mode":
        structured_llm = llm.with_structured_output(schema, method="json_mode")
    else:
        structured_llm = llm.with_structured_output(schema)

    result = structured_llm.invoke(prompt)
    return result


def json_output(
    prompt: str,
    system_instruction: str = "Respond only with valid JSON.",
    model: str = DEFAULT_PRO_MODEL,
    temperature: float = 0.0,
    max_tokens: int = None,
    **kwargs: Any,
) -> Dict:
    """
    Makes an LLM call that forces JSON output using generation config.
    Parses the response to a Python dict.

    Example usage:
    response = json_output("List 3 fruits as JSON array.")
    print(response)  # e.g., {"fruits": ["apple", "banana", "cherry"]}

    :param prompt: The input prompt string.
    :param system_instruction: System prompt to enforce JSON (optional).
    :param model: The Gemini model to use.
    :param temperature: Randomness control (low for JSON).
    :param max_tokens: Max response tokens.
    :param kwargs: Additional LLM init params.
    :return: Parsed JSON as a dict.
    """
    import json

    llm = _get_llm(
        model,
        temperature,
        max_tokens,
        response_mime_type="application/json",
        **kwargs,
    )
    messages = [SystemMessage(content=system_instruction), HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    content = _coerce_content_to_text(response.content).strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        metadata = getattr(response, "response_metadata", {}) or {}
        finish_reason = metadata.get("finish_reason")
        snippet = content[:500]
        logger.debug(
            "Gemini JSON decode failed. finish_reason=%s snippet=%r",
            finish_reason,
            snippet,
        )
        if finish_reason == "MAX_TOKENS":
            raise ValueError(
                "Gemini response truncated before completing JSON (finish_reason=MAX_TOKENS). "
                "Increase max_tokens or adjust the prompt for shorter output."
            ) from exc
        raise ValueError("Failed to parse JSON from response: " + snippet) from exc
