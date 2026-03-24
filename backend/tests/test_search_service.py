from app.services.search_service import SearchService


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
