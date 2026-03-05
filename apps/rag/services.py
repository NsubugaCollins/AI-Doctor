import logging
import os
import json
import hashlib
from typing import List, Dict, Any, Optional
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from django.conf import settings

# Use our simple text splitter
from .text_splitter import SimpleTextSplitter

logger = logging.getLogger(__name__)

class PDFRAGService:
    """RAG Service for PDF medical documents"""
    
    def __init__(self):
        self.pdf_directory = getattr(settings, 'PDF_STORAGE_PATH', 'data/medical_pdfs')
        self.chroma_path = getattr(settings, 'CHROMA_DB_PATH', 'data/chroma_db')
        
        # Initialize sentence transformer
        try:
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            logger.warning("Error loading sentence transformer: %s", e)
            logger.warning("Sentence transformer not available. PDF search will not work.")
            self.embedding_model = None
        
        self.dimension = 384
        self.index = None
        self.documents = []
        
        # Initialize simple text splitter
        self.text_splitter = SimpleTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        
        # Create directories if they don't exist
        os.makedirs(self.pdf_directory, exist_ok=True)
        os.makedirs(self.chroma_path, exist_ok=True)
        
        self._initialize_index()
    
    def _initialize_index(self):
        """Initialize or load FAISS index"""
        index_path = os.path.join(self.chroma_path, 'faiss.index')
        docs_path = os.path.join(self.chroma_path, 'documents.json')
        
        if os.path.exists(index_path) and os.path.exists(docs_path):
            try:
                self.index = faiss.read_index(index_path)
                with open(docs_path, 'r') as f:
                    self.documents = json.load(f)
                logger.info("Loaded existing index with %s documents", len(self.documents))
            except Exception as e:
                logger.warning("Error loading index (%s). Creating new one.", e)
                self.index = faiss.IndexFlatL2(self.dimension)
                self.documents = []
        else:
            self.index = faiss.IndexFlatL2(self.dimension)
            self.documents = []
            logger.info("Created new FAISS index")
    
    def _save_index(self):
        """Save FAISS index"""
        if self.index and self.documents:
            index_path = os.path.join(self.chroma_path, 'faiss.index')
            docs_path = os.path.join(self.chroma_path, 'documents.json')
            
            try:
                faiss.write_index(self.index, index_path)
                with open(docs_path, 'w') as f:
                    json.dump(self.documents, f, indent=2)
                logger.info("Saved index with %s documents", len(self.documents))
            except Exception as e:
                logger.warning("Error saving index: %s", e)
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF"""
        text = ""
        try:
            reader = PdfReader(pdf_path)
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += f"[Page {page_num + 1}]\n{page_text}\n\n"
            return text
        except Exception as e:
            logger.warning("Error extracting PDF %s: %s", pdf_path, e)
            return ""
    
    def load_pdf(self, pdf_path: str, metadata: Optional[Dict] = None) -> bool:
        """Load PDF into vector store"""
        if not self.embedding_model:
            logger.warning("Cannot load PDF: embedding model not available")
            return False
        
        try:
            logger.info("Loading PDF: %s", os.path.basename(pdf_path))
            
            # Extract text
            text = self.extract_text_from_pdf(pdf_path)
            if not text or len(text.strip()) < 50:
                logger.warning("PDF contains little text")
                return False
            
            logger.info("Extracted %s characters", len(text))
            
            # Split into chunks
            chunks = self.text_splitter.split_text(text)
            logger.info("Created %s chunks", len(chunks))
            
            if not chunks:
                return False
            
            # Create embeddings
            embeddings = self.embedding_model.encode(chunks)
            logger.info("Created embeddings with shape %s", getattr(embeddings, "shape", None))
            
            # Add to index
            if self.index.ntotal == 0:
                self.index = faiss.IndexFlatL2(self.dimension)
            self.index.add(embeddings.astype('float32'))
            
            # Store documents
            base_name = os.path.basename(pdf_path)
            for i, chunk in enumerate(chunks):
                self.documents.append({
                    'id': hashlib.md5(f"{base_name}_{i}".encode()).hexdigest()[:8],
                    'content': chunk[:500] + "..." if len(chunk) > 500 else chunk,
                    'full_content': chunk,
                    'source': base_name,
                    'chunk_index': i,
                    'metadata': metadata or {}
                })
            
            self._save_index()
            logger.info("Successfully loaded %s chunks from %s", len(chunks), base_name)
            return True
            
        except Exception as e:
            logger.exception("Error loading PDF: %s", e)
            return False
    
    def search_similar_sync(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar content"""
        if not self.embedding_model or not self.index or self.index.ntotal == 0:
            logger.info("No documents in index")
            return []
        
        try:
            # Create query embedding
            query_embedding = self.embedding_model.encode([query])
            
            # Search
            k = min(k, self.index.ntotal)
            if k == 0:
                return []
                
            distances, indices = self.index.search(query_embedding.astype('float32'), k)
            
            # Return results
            results = []
            for i, idx in enumerate(indices[0]):
                if 0 <= idx < len(self.documents):
                    doc = self.documents[idx].copy()
                    # Convert distance to similarity score (0-1)
                    similarity = 1 / (1 + distances[0][i])
                    doc['similarity_score'] = float(similarity)
                    
                    # Remove full_content to keep response size manageable
                    if 'full_content' in doc:
                        doc['content'] = doc['full_content'][:500] + "..." if len(doc['full_content']) > 500 else doc['full_content']
                        del doc['full_content']
                    
                    results.append(doc)
            
            return results
            
        except Exception as e:
            logger.warning("Error searching: %s", e)
            return []
    
    def get_pdf_sources(self) -> List[str]:
        """Get list of loaded PDF sources"""
        sources = set()
        for doc in self.documents:
            sources.add(doc.get('source', 'Unknown'))
        return list(sources)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the RAG system"""
        return {
            'total_documents': len(self.documents),
            'total_chunks': len(self.documents),
            'unique_sources': len(self.get_pdf_sources()),
            'index_size': self.index.ntotal if self.index else 0,
            'pdf_directory': str(self.pdf_directory),
            'chroma_path': str(self.chroma_path)
        }