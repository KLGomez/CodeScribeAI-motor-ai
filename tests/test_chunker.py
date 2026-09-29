from app.core.chunker import chunk_files


def test_chunk_files_basic():
    sample_files = [("src/main.py", "def foo():\n    return 42\n" * 30)]
    chunks = chunk_files(sample_files)
    assert len(chunks) > 0
    assert "filepath" in chunks[0]
    assert "chunk" in chunks[0]


def test_chunk_files_empty():
    chunks = chunk_files([("empty.py", "")])
    assert len(chunks) == 0
