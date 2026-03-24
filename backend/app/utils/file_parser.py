"""
File parsing utilities
Supports text extraction from PDF, Markdown, and TXT files
"""

import os
from pathlib import Path
from typing import Callable, List, Optional


def _read_text_with_fallback(file_path: str) -> str:
    """
    Read a text file, automatically detecting the encoding if UTF-8 fails.

    Uses a multi-level fallback strategy:
    1. First attempt UTF-8 decoding
    2. Use charset_normalizer to detect encoding
    3. Fall back to chardet for encoding detection
    4. Final fallback: UTF-8 with errors='replace'

    Args:
        file_path: Path to the file

    Returns:
        Decoded text content
    """
    data = Path(file_path).read_bytes()

    # First attempt UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # Try charset_normalizer to detect encoding
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass

    # Fall back to chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass

    # Final fallback: UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'

    return data.decode(encoding, errors='replace')


class FileParser:
    """File parser"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}

    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        Extract text from a file

        Args:
            file_path: Path to the file

        Returns:
            Extracted text content
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = path.suffix.lower()

        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {suffix}")

        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)

        raise ValueError(f"Cannot process file format: {suffix}")

    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """Extract text from a PDF file"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF is required: pip install PyMuPDF")

        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """Extract text from a Markdown file with automatic encoding detection"""
        return _read_text_with_fallback(file_path)

    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """Extract text from a TXT file with automatic encoding detection"""
        return _read_text_with_fallback(file_path)

    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        Extract text from multiple files and merge them

        Args:
            file_paths: List of file paths

        Returns:
            Merged text
        """
        all_texts = []

        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== Document {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== Document {i}: {file_path} (extraction failed: {str(e)}) ===")

        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    on_progress: Optional[Callable[[float], None]] = None,
) -> List[str]:
    """
    Split text into smaller chunks

    Args:
        text: Original text
        chunk_size: Number of characters per chunk
        overlap: Number of overlapping characters between chunks
        on_progress: Optional callback with fraction in [0, 1] while scanning text

    Returns:
        List of text chunks
    """
    total = len(text)
    if total == 0:
        if on_progress:
            on_progress(1.0)
        return []

    if total <= chunk_size:
        if on_progress:
            on_progress(1.0)
        return [text] if text.strip() else []

    chunks = []
    start = 0
    last_bucket = -1

    def _emit_progress() -> None:
        nonlocal last_bucket
        if not on_progress:
            return
        bucket = min(199, int((start / total) * 200))
        if bucket > last_bucket:
            last_bucket = bucket
            on_progress(min(1.0, start / total))

    while start < total:
        _emit_progress()
        end = start + chunk_size

        if end < total:
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < total else total

    if on_progress:
        on_progress(1.0)

    return chunks
