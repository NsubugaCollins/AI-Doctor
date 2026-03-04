"""
Simple text splitter for RAG system
No external dependencies - compatible with Python 3.14+
"""

import re
from typing import List, Optional, Dict, Any

class SimpleTextSplitter:
    """
    A simple text splitter that splits text into chunks
    No external dependencies, compatible with Python 3.14+
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None
    ):
        """
        Initialize the text splitter
        
        Args:
            chunk_size: Maximum size of each chunk
            chunk_overlap: Overlap between chunks
            separators: List of separators to use for splitting
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ".", "!", "?", ";", ":", " ", ""]
    
    def split_text(self, text: str) -> List[str]:
        """
        Split text into chunks
        
        Args:
            text: The text to split
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
        
        # Remove extra whitespace but preserve paragraph structure
        text = re.sub(r'\s+', ' ', text).strip()
        
        # If text is shorter than chunk size, return as is
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            # Calculate end position
            end = min(start + self.chunk_size, text_length)
            
            # If we're not at the end, try to find a good breaking point
            if end < text_length:
                end = self._find_break_point(text, start, end)
            
            # Add the chunk
            chunk = text[start:end].strip()
            if chunk:  # Only add non-empty chunks
                chunks.append(chunk)
            
            # Move start position, accounting for overlap
            start = max(end - self.chunk_overlap, start + 1)
            
            # Ensure we're making progress
            if start >= end:
                start = end
        
        return chunks
    
    def _find_break_point(self, text: str, start: int, end: int) -> int:
        """
        Find a good break point within the text segment
        
        Args:
            text: The full text
            start: Start position
            end: End position
            
        Returns:
            New end position at a good break point
        """
        segment = text[start:end]
        
        # Try each separator in order
        for separator in self.separators:
            if separator == "":
                break
            
            # Find the last occurrence of separator in the segment
            last_sep = segment.rfind(separator)
            if last_sep != -1 and last_sep > len(segment) // 2:
                return start + last_sep + len(separator)
        
        # If no good separator found, try to find any whitespace
        last_space = segment.rfind(' ')
        if last_space != -1 and last_space > len(segment) // 2:
            return start + last_space + 1
        
        # Last resort - just cut at end
        return end
    
    def split_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Split documents into chunks
        
        Args:
            documents: List of document dicts with 'content' and optional 'metadata'
            
        Returns:
            List of chunk dicts with 'content' and 'metadata'
        """
        all_chunks = []
        
        for doc in documents:
            content = doc.get('content', '')
            metadata = doc.get('metadata', {})
            
            chunks = self.split_text(content)
            
            for i, chunk in enumerate(chunks):
                chunk_metadata = metadata.copy()
                chunk_metadata['chunk_index'] = i
                chunk_metadata['total_chunks'] = len(chunks)
                
                all_chunks.append({
                    'content': chunk,
                    'metadata': chunk_metadata
                })
        
        return all_chunks
    
    def split_text_with_metadata(self, text: str, metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Split text into chunks and return with metadata
        
        Args:
            text: The text to split
            metadata: Optional metadata to attach to each chunk
            
        Returns:
            List of chunk dicts with 'content' and 'metadata'
        """
        chunks = self.split_text(text)
        metadata = metadata or {}
        
        result = []
        for i, chunk in enumerate(chunks):
            chunk_metadata = metadata.copy()
            chunk_metadata['chunk_index'] = i
            chunk_metadata['total_chunks'] = len(chunks)
            
            result.append({
                'content': chunk,
                'metadata': chunk_metadata
            })
        
        return result