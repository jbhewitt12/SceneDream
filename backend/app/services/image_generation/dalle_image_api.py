# dalle_image_api.py
#
# This Python module provides utility functions to interact with OpenAI's DALL·E 3 image generation API.
# It uses the official OpenAI Python library (version 2.2.0 or later recommended).
#
# Installation:
#   pip install openai
#
# Requirements:
#   - An OpenAI API key (obtain from https://platform.openai.com/account/api-keys)
#   - Python 3.8 or higher
#
# Usage:
#   Import this module and call the generate_images function with appropriate parameters.
#   Example:
#       from dalle_image_api import generate_images
#       api_key = "your_openai_api_key"
#       prompts = "A futuristic cityscape at sunset"
#       results = generate_images(prompts, api_key)
#       for result in results:
#           print(result)  # Prints URLs or base64 strings depending on response_format
#
# Note: DALL·E 3 has specific limitations:
#   - n=1 (only one image per request)
#   - Prompt length up to 4000 characters
#   - Sizes: '1024x1024', '1024x1792', '1792x1024'
#   - Quality: 'standard' (default, faster/cheaper) or 'hd' (higher quality, slower/more expensive)
#   - Style: 'vivid' (hyper-real, dramatic) or 'natural' (more natural-looking)
#   - Response format: 'url' (returns expiring URLs, typically valid for 1 hour) or 'b64_json' (returns base64-encoded image data)
#
# For more details, refer to the official OpenAI documentation:
#   https://platform.openai.com/docs/guides/images/image-generation

import base64
import os
import requests
from typing import List, Union

from openai import OpenAI


def generate_images(
    prompt: str,
    api_key: str,
    model: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
    n: int = 1,
    response_format: str = "url"
) -> List[Union[str, bytes]]:
    """
    Generates images using OpenAI's DALL·E model based on the provided text prompt.

    Parameters:
    - prompt (str): A text description of the desired image. Maximum length is 4000 characters for DALL·E 3.
      The prompt should be descriptive and clear to get the best results. Avoid including sensitive or harmful content,
      as OpenAI's moderation filters may reject such requests.

    - api_key (str): Your OpenAI API key for authentication.

    - model (str, optional): The model to use for generation. Defaults to "dall-e-3".
      Other options include "dall-e-2" for the previous version, but DALL·E 3 is recommended for better quality.

    - size (str, optional): The size of the generated images. Defaults to "1024x1024".
      For DALL·E 3, valid options are:
        - "1024x1024" (square)
        - "1024x1792" (portrait)
        - "1792x1024" (landscape)
      For DALL·E 2, valid options are "256x256", "512x512", "1024x1024".

    - quality (str, optional): The quality of the generated image. Defaults to "standard".
      Valid options (DALL·E 3 only):
        - "standard": Faster generation, lower cost.
        - "hd": Higher detail and consistency, but slower and more expensive.

    - style (str, optional): The style of the generated image. Defaults to "vivid".
      Valid options (DALL·E 3 only):
        - "vivid": Generates hyper-real and dramatic images.
        - "natural": Produces more natural, less hyper-real images.

    - n (int, optional): The number of images to generate. Defaults to 1.
      For DALL·E 3, this must be 1 (API limitation). For DALL·E 2, up to 10 is allowed.

    - response_format (str, optional): The format of the response data. Defaults to "url".
      Valid options:
        - "url": Returns a list of URLs to the generated images (expiring after ~1 hour).
        - "b64_json": Returns a list of base64-encoded image data strings.

    Returns:
    - List[Union[str, bytes]]: A list containing either image URLs (str) or base64-encoded image data (str),
      depending on the response_format. If an error occurs, an empty list is returned.

    Raises:
    - openai.error.OpenAIError: If there's an issue with the API request (e.g., invalid API key, rate limits).

    Example:
        results = generate_images(
            prompt="A serene mountain landscape with a lake",
            api_key="sk-your-api-key",
            size="1792x1024",
            quality="hd",
            style="natural",
            response_format="b64_json"
        )
        # If b64_json, results[0] is a base64 string; you can decode it to bytes if needed.
    """
    client = OpenAI(api_key=api_key)

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality if model == "dall-e-3" else None,  # Quality only for DALL·E 3
            style=style if model == "dall-e-3" else None,      # Style only for DALL·E 3
            n=n,
            response_format=response_format
        )

        if response_format == "url":
            return [data.url for data in response.data]
        elif response_format == "b64_json":
            return [data.b64_json for data in response.data]
        else:
            return []

    except Exception as e:
        print(f"Error generating images: {e}")
        return []


def save_image_from_url(url: str, filename: str) -> bool:
    """
    Downloads and saves an image from a URL to a local file.

    Parameters:
    - url (str): The URL of the image to download.
    - filename (str): The path and name of the file to save (e.g., "image.png").

    Returns:
    - bool: True if the image was saved successfully, False otherwise.

    Example:
        save_image_from_url("https://example.com/image.png", "local_image.png")
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(filename, "wb") as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"Error saving image from URL: {e}")
        return False


def save_image_from_b64(b64_data: str, filename: str) -> bool:
    """
    Decodes and saves a base64-encoded image string to a local file.

    Parameters:
    - b64_data (str): The base64-encoded image data.
    - filename (str): The path and name of the file to save (e.g., "image.png").

    Returns:
    - bool: True if the image was saved successfully, False otherwise.

    Example:
        save_image_from_b64("base64stringhere", "local_image.png")
    """
    try:
        image_data = base64.b64decode(b64_data)
        with open(filename, "wb") as f:
            f.write(image_data)
        return True
    except Exception as e:
        print(f"Error saving image from base64: {e}")
        return False