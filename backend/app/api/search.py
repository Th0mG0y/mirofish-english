"""
Search API routes
Provides web search, document enrichment, and fact-checking endpoints
"""

import traceback
from flask import request, jsonify

from . import search_bp
from ..utils.logger import get_logger
from ..services.search_service import SearchService

logger = get_logger('mirofish.api.search')

# Shared service instance
_search_service = None


def _get_search_service():
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service


@search_bp.route('/query', methods=['POST'])
def search_query():
    """
    Direct web search

    Request (JSON):
        {
            "query": "search query string",
            "context": "optional context"
        }

    Returns:
        {
            "success": true,
            "data": {
                "query": "...",
                "answer": "...",
                "citations": [{"url": "...", "title": "...", "snippet": "..."}]
            }
        }
    """
    try:
        data = request.get_json() or {}
        query = data.get('query')
        context = data.get('context', '')

        if not query:
            return jsonify({"success": False, "error": "Please provide query"}), 400

        service = _get_search_service()
        result = service.search(query=query, context=context)

        return jsonify({
            "success": True,
            "data": {
                "query": result.query,
                "answer": result.answer,
                "citations": [
                    {"url": c.url, "title": c.title, "snippet": c.snippet}
                    for c in result.citations
                ]
            }
        })

    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@search_bp.route('/enrich', methods=['POST'])
def enrich_document():
    """
    Enrich a document with web search context

    Request (JSON):
        {
            "document_text": "text to enrich",
            "requirement": "research requirement"
        }

    Returns:
        {
            "success": true,
            "data": {
                "queries_used": [...],
                "supplementary_context": "...",
                "citations": [...],
                "total_sources": 5
            }
        }
    """
    try:
        data = request.get_json() or {}
        document_text = data.get('document_text', '')
        requirement = data.get('requirement', '')

        if not document_text and not requirement:
            return jsonify({"success": False, "error": "Please provide document_text or requirement"}), 400

        service = _get_search_service()
        result = service.enrich_document(document_text=document_text, requirement=requirement)

        return jsonify({
            "success": True,
            "data": {
                "queries_used": result.queries_used,
                "supplementary_context": result.supplementary_context,
                "citations": [
                    {"url": c.url, "title": c.title, "snippet": c.snippet}
                    for c in result.citations
                ],
                "total_sources": result.total_sources
            }
        })

    except Exception as e:
        logger.error(f"Enrichment failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@search_bp.route('/fact-check', methods=['POST'])
def fact_check():
    """
    Fact-check a claim

    Request (JSON):
        {
            "claim": "claim to fact-check"
        }

    Returns:
        {
            "success": true,
            "data": {
                "claim": "...",
                "verdict": "supported|contradicted|inconclusive",
                "confidence": 0.8,
                "explanation": "...",
                "supporting_sources": [...],
                "contradicting_sources": [...]
            }
        }
    """
    try:
        data = request.get_json() or {}
        claim = data.get('claim', '')

        if not claim:
            return jsonify({"success": False, "error": "Please provide claim"}), 400

        service = _get_search_service()
        result = service.fact_check(claim=claim)

        return jsonify({
            "success": True,
            "data": {
                "claim": result.claim,
                "verdict": result.verdict,
                "confidence": result.confidence,
                "explanation": result.explanation,
                "supporting_sources": [
                    {"url": c.url, "title": c.title, "snippet": c.snippet}
                    for c in result.supporting_sources
                ],
                "contradicting_sources": [
                    {"url": c.url, "title": c.title, "snippet": c.snippet}
                    for c in result.contradicting_sources
                ]
            }
        })

    except Exception as e:
        logger.error(f"Fact-check failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@search_bp.route('/log', methods=['GET'])
def search_log():
    """
    View search history

    Returns:
        {
            "success": true,
            "data": {
                "searches": [...],
                "total": 10
            }
        }
    """
    try:
        service = _get_search_service()
        log = service.get_search_log()

        return jsonify({
            "success": True,
            "data": {
                "searches": log,
                "total": len(log)
            }
        })

    except Exception as e:
        logger.error(f"Failed to get search log: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
