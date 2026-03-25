from app.services.search_service import SearchService
from app.utils.llm_provider import Citation, ProviderResponse, WebSearchResult


class NoSearchProvider:
    def supports_web_search(self):
        return False

    def web_search(self, query: str, context: str = ""):
        raise AssertionError("web_search should not be called when the provider does not support it")


def test_search_service_returns_clear_message_for_non_search_provider():
    service = SearchService(provider=NoSearchProvider())
    result = service.search("test query")

    assert "does not support built-in web search" in result.answer
    assert result.citations == []


class EnrichmentProvider:
    def supports_web_search(self):
        return True

    def chat(self, **kwargs):
        return ProviderResponse(content='{"queries": ["market adoption outlook"]}')

    def web_search(self, query: str, context: str = ""):
        return WebSearchResult(
            query=query,
            answer="Analysts expect uneven adoption driven by trust and channel fit.",
            citations=[
                Citation(
                    url="https://example.com/source-1",
                    title="Source One",
                    snippet="First supporting source.",
                ),
                Citation(
                    url="https://example.com/source-1",
                    title="Source One",
                    snippet="Duplicate entry should be removed.",
                ),
            ],
        )


def test_enrich_document_includes_source_links_and_dedupes():
    service = SearchService(provider=EnrichmentProvider())
    result = service.enrich_document("Document body", "Assess adoption risk")

    assert result.total_sources == 1
    assert "### market adoption outlook" in result.supplementary_context
    assert "**Sources**" in result.supplementary_context
    assert "https://example.com/source-1" in result.supplementary_context


def test_search_service_records_search_intent_metadata():
    service = SearchService(provider=EnrichmentProvider())

    service.search(
        "market adoption outlook",
        context="fresh context",
        intent="verification",
        report_question="How strong is adoption?",
        evidence_type="benchmark_data",
    )

    log = service.get_search_log()

    assert log[0]["intent"] == "verification"
    assert log[0]["report_question"] == "How strong is adoption?"
    assert log[0]["evidence_type"] == "benchmark_data"
