"""
Django management command to load medical PDFs into the RAG system
"""

import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.rag.services import PDFRAGService


class Command(BaseCommand):
    help = 'Load medical PDF documents into the RAG vector database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--directory',
            type=str,
            default=None,
            help='Directory containing PDF files (default: data/medical_pdfs)'
        )
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Load a specific PDF file'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing index before loading'
        )

    def handle(self, *args, **options):
        directory = options['directory']
        file_path = options['file']
        clear = options['clear']
        
      
        self.stdout.write(self.style.SUCCESS('PDF RAG System Loader'))
        
        
        # Initialize RAG service
        rag_service = PDFRAGService()
        
        if clear:
            self.stdout.write(self.style.WARNING(' Clearing existing index...'))
            # Reset index
            import faiss
            rag_service.index = faiss.IndexFlatL2(rag_service.dimension)
            rag_service.documents = []
            rag_service._save_index()
            self.stdout.write(self.style.SUCCESS(' Index cleared'))
        
        # Determine PDF directory
        if directory:
            pdf_dir = Path(directory)
        elif file_path:
            pdf_dir = None
        else:
            pdf_dir = Path(getattr(settings, 'PDF_STORAGE_PATH', 'data/medical_pdfs'))
        
        # Load single file
        if file_path:
            file_path = Path(file_path)
            if not file_path.exists():
                self.stdout.write(self.style.ERROR(f' File not found: {file_path}'))
                return
            
            self.stdout.write(f'\n Loading: {file_path.name}')
            success = rag_service.load_pdf(str(file_path))
            
            if success:
                self.stdout.write(self.style.SUCCESS(f' Successfully loaded {file_path.name}'))
            else:
                self.stdout.write(self.style.ERROR(f' Failed to load {file_path.name}'))
            
            self._print_stats(rag_service)
            return
        
        # Load directory
        if not pdf_dir.exists():
            self.stdout.write(self.style.WARNING(f'  Directory not found: {pdf_dir}'))
            self.stdout.write(f'Creating directory: {pdf_dir}')
            pdf_dir.mkdir(parents=True, exist_ok=True)
            self.stdout.write(self.style.SUCCESS(f'\n Created directory. Please add PDF files to: {pdf_dir}'))
            self.stdout.write('Then run this command again.')
            return
        
        # Find all PDFs
        pdf_files = list(pdf_dir.glob('**/*.pdf'))
        
        if not pdf_files:
            self.stdout.write(self.style.WARNING(f'\n  No PDF files found in {pdf_dir}'))
            self.stdout.write(f'Please add PDF files to: {pdf_dir}')
            return
        
        self.stdout.write(f'\n Found {len(pdf_files)} PDF files in {pdf_dir}\n')
        
        # Load each PDF
        success_count = 0
        fail_count = 0
        
        for idx, pdf_file in enumerate(pdf_files, 1):
            self.stdout.write(f'[{idx}/{len(pdf_files)}]  Loading: {pdf_file.name}')
            
            try:
                success = rag_service.load_pdf(
                    str(pdf_file),
                    metadata={
                        'filename': pdf_file.name,
                        'path': str(pdf_file),
                        'loaded_at': str(Path.cwd())
                    }
                )
                
                if success:
                    self.stdout.write(self.style.SUCCESS(f'     Success'))
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f'     Failed'))
                    fail_count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'     Error: {e}'))
                fail_count += 1
        
        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS(f' Successfully loaded: {success_count} PDFs'))
        if fail_count > 0:
            self.stdout.write(self.style.ERROR(f' Failed to load: {fail_count} PDFs'))
        
        self._print_stats(rag_service)
    
    def _print_stats(self, rag_service):
        """Print RAG system statistics"""
        stats = rag_service.get_stats()
        
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS(' RAG System Statistics'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'Total documents: {stats["total_documents"]}')
        self.stdout.write(f'Total chunks: {stats["total_chunks"]}')
        self.stdout.write(f'Unique sources: {stats["unique_sources"]}')
        self.stdout.write(f'Index size: {stats["index_size"]} vectors')
        self.stdout.write(f'PDF directory: {stats["pdf_directory"]}')
        self.stdout.write(f'Index path: {stats["chroma_path"]}')
        
        # List sources
        sources = rag_service.get_pdf_sources()
        if sources:
            self.stdout.write(f'\n Loaded sources:')
            for source in sorted(sources):
                self.stdout.write(f'  - {source}')
        
        self.stdout.write('\n' + '=' * 70)
