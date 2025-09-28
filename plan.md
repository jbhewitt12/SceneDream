# Plan

## Overview

I want to get books written by authors like Ian M. Banks in text format (like epub). Then, I want to use an LLM to extract scenes from the book that would be able to be turned into incredible-looking images or videos. Next, I want to rank the scenes and use an LLM to turn those descriptions into a description that will work well as a prompt for AI image generation. Finally, I want to generate those images or videos.


## Files that already exist

- requirements.txt already exists with these dependencies:
```
langchain==0.3.27
langchain-community==0.3.30
langchain-google-genai==2.1.12
langchain-xai==0.2.5
ebooklib==0.19
```

- .venv already exists and is activated.

- a /Books folder already exists that contains subdirectories that contain the book files. Start with `Books/Iain Banks/Excession/Excession - Iain M. Banks.epub`

- A .env file already exists with the following variables:
```
OPENAI_API_KEY
XAI_API_KEY
GEMINI_API_KEY
```

## Steps

1. Set up

- Create gemini_api.py and xai_api.py that contain methods that use Langchain to call Gemini and XAI respectively. The methods should be general and handle both simple LLM calls and LLM calls with functions.

gemini_api.py
```
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool  # For function/tool binding
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def call_gemini(model_name: str, prompt: str, system_prompt: str = None, tools=None, json_mode=False):
    """
    General method to call Gemini. Handles simple calls or with tools.
    - If tools provided, binds them and parses tool calls.
    - For JSON output, use system prompt to enforce.
    """
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=GEMINI_API_KEY,
        temperature=0.7,  # Adjustable
        max_tokens=4096   # Adjust based on needs
    )
    
    if tools:
        llm_with_tools = llm.bind_tools(tools)
        # Example: If tools, invoke and handle tool calls
        response = llm_with_tools.invoke([HumanMessage(content=prompt)])
        if response.tool_calls:
            # Handle tool execution here if needed; for now, assume simple
            return {"tool_calls": response.tool_calls, "content": response.content}
        return response.content
    else:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        response = llm.invoke(messages)
        return response.content

# Example usage:
# result = call_gemini("gemini-2.5-pro", "Hello world")
# For JSON: Add to system_prompt: "Respond in JSON format only."
```

xai_api.py
```
import os
from dotenv import load_dotenv
from langchain_xai import ChatXAI
from langchain_core.tools import tool  # For function/tool binding
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")

def call_xai(model_name: str, prompt: str, system_prompt: str = None, tools=None, json_mode=False):
    """
    General method to call Grok. Handles simple calls or with tools.
    - If tools provided, binds them and parses tool calls.
    - For JSON output, use system prompt to enforce.
    """
    llm = ChatXAI(
        model=model_name,
        api_key=XAI_API_KEY,
        temperature=0.7,  # Adjustable
        max_tokens=8192   # Grok supports larger contexts
    )
    
    if tools:
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke([HumanMessage(content=prompt)])
        if response.tool_calls:
            return {"tool_calls": response.tool_calls, "content": response.content}
        return response.content
    else:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        response = llm.invoke(messages)
        return response.content

# Example usage:
# result = call_xai("grok-4", "Hello world")
# For JSON: Add to system_prompt: "Respond in JSON format only."
```

utils.py: Helper functions, e.g., EPUB ingestion.
```
import logging
import os
import json
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
import yaml
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, filename='logs/pipeline.log')

def load_config():
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)

def read_epub(book_path):
    try:
        book = epub.read_epub(book_path)
        chapters = []
        chapter_num = 1
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                content = item.get_content().decode('utf-8')
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)
                chapters.append({
                    "chapter_num": chapter_num,
                    "text": text,
                    "title": item.get_name()  # Or from TOC
                })
                chapter_num += 1
        return chapters
    except Exception as e:
        logging.error(f"Error reading EPUB: {e}")
        return []

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

# Parallel processing helper
def process_in_parallel(func, items, max_workers=4):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(func, items))
```

2. Extract Scenes with LLM

- Ingest the full .epub text. Split it into chapters. For each chapter, load it into the latest Gemini 2.5 pro model (using gemini_api.py) with a prompt like: "Scan the chapter and extract every single descriptive scene that is visually rich, action-packed, or atmospheric—ideal for turning into images/videos. Focus on elements that would be great for images or videos. Output each scene verbatim with page references. Ensure you copy all of the details of the scene. It's fine if it is a big chunk of text because it may be used to create multiple images/videos. Output each scene as a JSON object." The prompt will need to be further refined, and the model should output JSON.

- Use a second LLM to refine (e.g., "Critique these extractions: Remove any that are too dialogue-heavy or abstract; enhance descriptions with sensory details from the text"). This iterates to ensure scenes are "image-ready" (vivid, concrete visuals).

- Make an `extracted_scenes` folder organized into subdirectories by book. Once a scene is extracted and refined save each scene as a JSON file. For each scene, we will start the file name with the chapter number, then a dash and then an integer that iterates for each scene file and then a short description of the scene. The integer will be unique and effectively be the ID of the scene.

3. Rank Scenes with LLM

- Use `grok-4-fast-reasoning` to score scenes on criteria like visual potential (e.g., scale of 1-10 for "epicness," "color vibrancy," "dynamic action"), feasibility for AI gen (e.g., avoid overly complex crowds if the tool struggles), and uniqueness.

- LLM-aggressive: Employ a "committee" of LLMs—query the same ranking prompt across 3-5 model instances (or variations) and average scores. To start with, only query Gemini flash as well. Add a feedback loop: "Re-rank based on why lower-scored scenes might improve with better prompting." Top 10-20 scenes proceed.

- Whenever ranking is done, update the file for that scene with standardized JSON that captures all the ranking information. 

4. Convert to Image Prompts with LLM

- For now, let's focus on just creating image prompts, not video prompts. This will make it easier to start with.

- For each ranked scene: LLM prompt `grok-4-fast-reasoning` like: "Transform this scene description into a detailed AI image prompt. Include style (e.g., cinematic, hyper-realistic), lighting, composition, and references to artists like Syd Mead for sci-fi vibes. Optimize for [tool name] to maximize quality."

- LLM-aggressive: Chain refinements—generate initial prompt, then use another LLM to critique ("Does this prompt avoid ambiguities? Suggest improvements for better output fidelity to the book"). Iterate 2-3 times per scene.

- Make an `image_prompts` folder organized into subdirectories by book. Once a prompt is generated and refined save each prompt as a JSON file. For each prompt, we will start the file name with the chapter number, then a dash and then an integer that is the same as the scene it matches and then a short description of the prompt. The integer will be unique and effectively be the ID of the prompt. The JSON should be structured so that there will be many alternates of the prompt potentially in the file.