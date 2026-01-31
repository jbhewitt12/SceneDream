import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import ebooklib
import yaml
from bs4 import BeautifulSoup
from ebooklib import epub

logging.basicConfig(level=logging.INFO, filename="logs/pipeline.log")


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def read_epub(book_path):
    try:
        book = epub.read_epub(book_path)
        chapters = []
        chapter_num = 1
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                content = item.get_content().decode("utf-8")
                soup = BeautifulSoup(content, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                chapters.append(
                    {
                        "chapter_num": chapter_num,
                        "text": text,
                        "title": item.get_name(),  # Or from TOC
                    }
                )
                chapter_num += 1
        return chapters
    except Exception as e:
        logging.error(f"Error reading EPUB: {e}")
        return []


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


# Parallel processing helper
def process_in_parallel(func, items, max_workers=4):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(func, items))
