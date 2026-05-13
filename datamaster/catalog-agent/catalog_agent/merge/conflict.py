import fnmatch
from typing import Any

CONFLICT_POLICY: dict[str, str] = {
    "price": "merchant",
    "inventory": "merchant",
    "primary_image": "merchant",
    "delivery_info": "merchant",
    "net_content": "external",
    "net_content_uom": "external",
    "ingredients": "external",
    "allergens": "external",
    "nutrition.*": "external",
    "country_of_origin": "external",
    "certifications": "external",
    "description": "gap_fill",
    "brand": "gap_fill",
    "color": "gap_fill",
    "size": "gap_fill",
    "material": "gap_fill",
    "mpn": "gap_fill",
    "title": "gap_fill",
    "gtin": "gap_fill",
    "category_gpc": "gap_fill",
    "packaging_type": "gap_fill",
}


def _resolve_policy(attribute: str, policy_override: dict | None) -> str:
    if policy_override and attribute in policy_override:
        return policy_override[attribute]
    if attribute in CONFLICT_POLICY:
        return CONFLICT_POLICY[attribute]
    for pattern, policy in CONFLICT_POLICY.items():
        if fnmatch.fnmatch(attribute, pattern):
            return policy
    return "gap_fill"


def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    if isinstance(val, (list, dict)) and len(val) == 0:
        return True
    return False


class ConflictResolver:
    def resolve(
        self,
        attribute: str,
        merchant_val: Any,
        external_val: Any,
        policy_override: dict | None = None,
    ) -> tuple[Any, str]:
        """Returns (resolved_value, decision_reason)."""
        policy = _resolve_policy(attribute, policy_override)

        if policy == "merchant":
            return merchant_val, "merchant_wins"

        if policy == "external":
            if not _is_empty(external_val):
                return external_val, "external_wins"
            return merchant_val, "external_empty_fallback_merchant"

        # gap_fill: external only if merchant is empty
        if _is_empty(merchant_val) and not _is_empty(external_val):
            return external_val, "gap_fill"
        return merchant_val, "merchant_has_value"

    def merge(
        self,
        baseline_attrs: dict,
        aligned_external: dict,
        policy_override: dict | None = None,
    ) -> tuple[dict, list[dict]]:
        """
        Merge aligned_external into baseline_attrs using conflict policies.
        Returns (merged_attrs, conflict_log).
        """
        merged = dict(baseline_attrs)
        conflict_log = []

        for attr, ext_val in aligned_external.items():
            if attr.startswith("_"):
                continue
            merchant_val = baseline_attrs.get(attr)
            resolved, reason = self.resolve(attr, merchant_val, ext_val, policy_override)
            if resolved != merchant_val:
                merged[attr] = resolved
            conflict_log.append({
                "attribute": attr,
                "merchant_val": merchant_val,
                "external_val": ext_val,
                "resolved_val": resolved,
                "decision": reason,
            })

        return merged, conflict_log
