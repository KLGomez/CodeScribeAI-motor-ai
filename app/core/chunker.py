from typing import List, Tuple
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import get_settings


def chunk_files(files: List[Tuple[str, str]]) -> List[dict]:
    """
    Splits file contents into manageable chunks for Gemini.
    Returns list of dicts with filepath, chunk text, chunk index, and total chunks.
    """
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
    )

    chunks = []
    for filepath, content in files:
        if not content.strip():
            continue
        file_chunks = splitter.split_text(content)
        for i, chunk in enumerate(file_chunks):
            chunks.append({
                "filepath": filepath,
                "chunk": chunk,
                "chunk_index": i,
                "total_chunks": len(file_chunks),
            })

    return chunks
