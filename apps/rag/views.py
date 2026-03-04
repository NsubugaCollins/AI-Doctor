from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .services import PDFRAGService
import os

rag_service = PDFRAGService()

@api_view(['POST'])
def upload_pdf(request):
    """Upload and process a PDF"""
    if 'file' not in request.FILES:
        return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    file = request.FILES['file']
    
    if not file.name.endswith('.pdf'):
        return Response({'error': 'File must be PDF'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Save file
    path = default_storage.save(f'pdfs/{file.name}', ContentFile(file.read()))
    full_path = default_storage.path(path)
    
    # Process PDF
    metadata = {
        'category': request.data.get('category', 'general'),
        'uploaded_by': str(request.user.id) if request.user.is_authenticated else 'anonymous'
    }
    
    success = rag_service.load_pdf(full_path, metadata)
    
    if success:
        return Response({
            'message': 'PDF loaded successfully',
            'filename': file.name,
            'chunks': len([d for d in rag_service.documents if d.get('source') == file.name])
        })
    else:
        return Response({'error': 'Failed to process PDF'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def search_pdfs(request):
    """Search PDF content"""
    query = request.GET.get('q', '')
    k = int(request.GET.get('k', 5))
    
    if not query:
        return Response({'error': 'No query provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    results = rag_service.search_similar_sync(query, k)
    
    return Response({
        'query': query,
        'results': results
    })

@api_view(['GET'])
def list_sources(request):
    """List all PDF sources"""
    sources = rag_service.get_pdf_sources()
    
    return Response({
        'total': len(sources),
        'sources': sources
    })