import hashlib
from typing import Any

FIELD_MAP: dict[str, dict[str, str]] = {
    "open_food_facts": {
        "product_name": "title",
        "brands": "brand",
        "quantity": "net_content",
        "ingredients_text": "ingredients",
        "allergens": "allergens",
        "nutriments.energy-kcal_100g": "nutrition.energy_kcal",
        "packaging": "packaging_type",
        "countries": "country_of_origin",
        "labels": "certifications",
    },
    "gs1": {
        "brandName": "brand",
        "netContent": "net_content",
        "netContentUom": "net_content_uom",
        "countryOfOrigin": "country_of_origin",
        "gpcCategoryCode": "category_gpc",
        "productDescription": "description",
    },
    "schema_org": {
        "name": "title",
        "brand.name": "brand",
        "color": "color",
        "size": "size",
        "material": "material",
        "description": "description",
        "mpn": "mpn",
        "gtin13": "gtin",
    },
}


def _get_nested(data: dict, dotted_key: str) -> Any:
    parts = dotted_key.split(".")
    val = data
    for part in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val


class SchemaAligner:
    def align(self, source: str, raw: dict) -> dict:
        """Map raw source fields to internal ontology. Unknown fields go to _unmapped."""
        mapping = FIELD_MAP.get(source, {})
        aligned: dict[str, Any] = {}
        unmapped: dict[str, Any] = {}

        # Map known fields
        for src_key, dst_key in mapping.items():
            val = _get_nested(raw, src_key)
            if val is not None and val != "" and val != []:
                aligned[dst_key] = val

        # Collect unmapped fields (top-level only, skip already mapped)
        mapped_src_keys = set(mapping.keys())
        for k, v in raw.items():
            if k not in mapped_src_keys and v is not None and v != "":
                unmapped[k] = v

        if unmapped:
            aligned["_unmapped"] = unmapped

        return aligned

    def coverage(self, aligned: dict, target_attributes: list[str]) -> dict[str, bool]:
        return {attr: attr in aligned and aligned[attr] not in (None, "", []) for attr in target_attributes}

    def fingerprint(self, aligned: dict) -> str:
        keys = sorted(k for k in aligned if not k.startswith("_"))
        return hashlib.sha256("|".join(keys).encode()).hexdigest()[:16]
