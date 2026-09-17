from ..config import settings
from .mock import MockPeople, MockPublic
from .apollo import ApolloProvider
from .serpapi import SerpAPIProvider, SerpAPIPeople
from .ai import MockAI, CompatibleAI
from .base import (
    PeopleSearchProvider,
    PeopleEnrichmentProvider,
    PublicSearchProvider,
    AIProvider,
)


def people_search() -> PeopleSearchProvider:
    return MockPeople() if settings.people_mode == "mock" else SerpAPIPeople()


def people_enrichment() -> PeopleEnrichmentProvider:
    return MockPeople() if settings.people_mode == "mock" else ApolloProvider()


def public_search() -> PublicSearchProvider:
    return MockPublic() if settings.public_search_mode == "mock" else SerpAPIProvider()


def ai() -> AIProvider:
    return MockAI() if settings.ai_mode == "mock" else CompatibleAI()
