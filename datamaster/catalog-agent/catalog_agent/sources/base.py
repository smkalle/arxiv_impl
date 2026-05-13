from abc import ABC, abstractmethod


class SourceAdapter(ABC):
    source_name: str

    @abstractmethod
    async def fetch(self, sku: dict) -> dict | None:
        """
        Takes SKU dict with keys: sku_id, gtin, jan, ean, brand, title, category_l2.
        Returns raw attribute dict from source, or None if not found.
        """
