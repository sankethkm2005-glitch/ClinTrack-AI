"""Provider-independent abstract base class for AI intelligence providers."""

from abc import ABC, abstractmethod
from app.schemas.document import ClinicalExtractionResult


class BaseAIProvider(ABC):
    """Abstract interface that all clinical AI providers must implement."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout: int = 60):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    @abstractmethod
    async def extract_clinical_data(
        self,
        filename: str,
        document_type: str,
        page_texts: list[dict],
    ) -> ClinicalExtractionResult:
        """Analyze page text and extract validated clinical facts."""
        pass
