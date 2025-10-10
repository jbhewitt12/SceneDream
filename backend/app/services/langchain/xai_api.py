# xai_api.py
# This file provides a Python wrapper using the LangChain library (latest version: 0.3.27 as of September 2025)
# to simplify making various types of LLM calls to xAI's Grok API. Since xAI's API is OpenAI-compatible,
# we use LangChain's ChatOpenAI class with a custom base URL.
#
# Assumptions:
# - You have an xAI API key. Obtain one from https://x.ai/api
# - The API base URL is 'https://api.x.ai/v1' (confirm at https://x.ai/api for latest)
# - Models like 'grok-beta' are available (check API docs for current models)
#
# This wrapper includes methods for:
# - Simple calls: Basic prompt to text response.
# - Calls with functions/tools: Bind tools to the model and handle tool calls.
# - Calls requiring JSON output: Enforce structured JSON output using Pydantic schemas or JSON schemas.
#
# Usage:
# - Initialize the class with your API key.
# - Call the appropriate method based on your needs.
#
# Comments are extensive for clarity, so a coding agent can easily understand and extend this.
# Inspired by examples from LangChain docs (e.g., https://python.langchain.com/docs/how_to/structured_output/),
# GitHub repos like Langchain-Chatchat's llm_api.py (which defines API endpoints for LLM interactions),
# and various tutorials on simple LLM chains, function calling, and structured outputs.
#
# Dependencies: Install via pip install langchain==0.3.27 langchain-openai
# Note: langchain-openai is used for OpenAI-compatible APIs.

from typing import List, Dict, Any, Optional, Union
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.tools import tool  # For defining tools
from langchain_core.pydantic_v1 import BaseModel  # For structured outputs
from pydantic import Field


class XAIAPI:
    """
    A class to handle various LLM calls to xAI's Grok API using LangChain.

    Attributes:
        api_key (str): Your xAI API key.
        base_url (str): The base URL for xAI API (default: 'https://api.x.ai/v1').
        model (str): The model name to use (default: 'grok-beta').
        llm: The initialized ChatOpenAI instance for making calls.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.x.ai/v1",
        model: str = "grok-beta",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        """
        Initializes the XAIAPI wrapper.

        Args:
            api_key: xAI API key.
            base_url: API endpoint base URL.
            model: Model name (e.g., 'grok-beta').
            temperature: Controls randomness (0-1).
            max_tokens: Max tokens in response.

        This sets up the LangChain ChatOpenAI with custom base_url for xAI compatibility.
        Example from LangChain docs: ChatOpenAI can be pointed to custom endpoints.
        """
        # Initialize the LLM with OpenAI-compatible settings for xAI
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self.model = model
        self.base_url = base_url

    def simple_call(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Makes a simple LLM call: prompt -> response as string.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system message for context.

        Returns:
            str: The LLM's response.

        This uses a basic ChatPromptTemplate and StrOutputParser.
        Inspired by simple LLM chain examples, e.g., from https://python.langchain.com/docs/tutorials/llm_chain/
        where a prompt template is chained to an LLM for translation or basic queries.
        """
        # Create a prompt template; if system_prompt, include it
        if system_prompt:
            template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("human", "{prompt}"),
                ]
            )
        else:
            template = PromptTemplate.from_template("{prompt}")

        # Chain: prompt -> LLM -> string output
        chain = template | self.llm | StrOutputParser()

        # Invoke the chain
        response = chain.invoke({"prompt": prompt})
        return response

    def call_with_functions(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        auto_execute: bool = False,
    ) -> Union[Dict[str, Any], Any]:
        """
        Makes an LLM call with function/tool calling.

        Args:
            prompt: The user prompt.
            tools: List of tool definitions (each as dict with 'type': 'function', 'function': {'name', 'description', 'parameters'}}).
            system_prompt: Optional system message.
            auto_execute: If True, automatically execute the called tool (assumes tools are callable Python functions).

        Returns:
            Dict or Any: Tool call response if tool called, else plain response. If auto_execute, returns tool result.

        This binds tools to the LLM and invokes. Handles tool calls manually if needed.
        Based on function calling examples from https://python.langchain.com/docs/how_to/function_calling/
        and concepts like binding tools with .bind_tools().
        For simplicity, we assume tools are in OpenAI-compatible format.
        Example tool: {'type': 'function', 'function': {'name': 'multiply', 'description': 'Multiply two numbers', 'parameters': {'type': 'object', 'properties': {'a': {'type': 'number'}, 'b': {'type': 'number'}}, 'required': ['a', 'b']}}}
        """
        # Bind tools to the LLM
        llm_with_tools = self.llm.bind_tools(tools)

        # Create prompt template
        if system_prompt:
            messages = [
                ("system", system_prompt),
                ("human", prompt),
            ]
        else:
            messages = [("human", prompt)]

        # Invoke LLM with tools
        response = llm_with_tools.invoke(messages)

        # Check if tool calls are present
        if response.tool_calls:
            tool_call = response.tool_calls[0]  # Assume single tool call for simplicity
            if auto_execute:
                # Find the tool function (assumes tools are callable; in practice, map names to functions)
                # For demo, you'd need to provide callable tools; here we simulate
                # Coding agent note: Extend this by mapping tool names to actual functions.
                tool_name = tool_call["name"]
                args = tool_call["args"]
                # Example: If tool is a Python @tool decorator, call it
                # But for now, return the call details
                return {
                    "tool_called": tool_name,
                    "args": args,
                    "note": "Auto-execute not implemented; implement function mapping.",
                }
            else:
                return {"tool_calls": response.tool_calls}
        else:
            return response.content

    def call_with_json_output(
        self,
        prompt: str,
        schema: Union[BaseModel, Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Makes an LLM call enforcing JSON structured output.

        Args:
            prompt: The user prompt.
            schema: Pydantic BaseModel class or JSON schema dict for output structure.
            system_prompt: Optional system message.

        Returns:
            Dict: Parsed JSON response matching the schema.

        Uses .with_structured_output() for enforcement.
        Inspired by structured output examples from https://python.langchain.com/docs/how_to/structured_output/
        and Pydantic/JSON schema usage in https://medium.com/@asmmorshedulhoque/mastering-structured-output-in-langchain-pydantic-typeddict-and-json-schema-573d67d5daa4
        Example schema: class Person(BaseModel): name: str = Field(description="Person's name")
        Or dict: {"type": "object", "properties": {"name": {"type": "string"}}}
        """
        # If schema is Pydantic, use it directly; else, use json_schema
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            llm_structured = self.llm.with_structured_output(schema)
        else:
            llm_structured = self.llm.with_structured_output(schema, method="json_mode")

        # Create prompt template
        if system_prompt:
            template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("human", "{prompt}"),
                ]
            )
        else:
            template = ChatPromptTemplate.from_messages([("human", "{prompt}")])

        # Chain: prompt -> structured LLM
        chain = template | llm_structured

        # Invoke and return dict
        response = chain.invoke({"prompt": prompt})
        return response


# Example usage (commented out; for testing)
# if __name__ == "__main__":
#     api = XAIAPI(api_key="your_xai_api_key_here")
#     # Simple call
#     print(api.simple_call("Hello, world!"))
#
#     # Function call example
#     @tool
#     def multiply(a: int, b: int) -> int:
#         """Multiply two numbers."""
#         return a * b
#     tools = [multiply]
#     print(api.call_with_functions("What is 5 times 3?", tools))
#
#     # JSON output
#     class Joke(BaseModel):
#         setup: str = Field(description="The setup of the joke")
#         punchline: str = Field(description="The punchline")
#     print(api.call_with_json_output("Tell me a joke", Joke))
