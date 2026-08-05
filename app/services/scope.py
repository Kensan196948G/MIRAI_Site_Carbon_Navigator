"""GHG Protocol scope classification for activity categories."""

SCOPE_BY_CATEGORY = {
    "fuel": "scope1",
    "machine": "scope1",
    "ship": "scope1",
    "power": "scope2",
    "material": "scope3",
    "transport": "scope3",
    "waste": "scope3",
    "business_travel": "scope3",
    "commuting": "scope3",
    "water": "scope3",
}

SCOPE_LABELS = {
    "scope1": "Scope1 直接排出",
    "scope2": "Scope2 エネルギー間接排出",
    "scope3": "Scope3 その他間接排出",
}

SCOPE_ORDER = ["scope1", "scope2", "scope3"]


def category_scope(category: str) -> str:
    return SCOPE_BY_CATEGORY.get(category, "scope3")


def scope_summary_from_results(results: list[dict]) -> list[dict]:
    """
    results: list of {"category": str, "co2_kg": float}
    Returns scope summary items with category breakdown.
    """
    totals: dict[str, dict] = {
        scope: {"scope": scope, "label": SCOPE_LABELS[scope], "by_category": {}, "total_co2_kg": 0.0}
        for scope in SCOPE_ORDER
    }
    for r in results:
        cat = r.get("category", "other")
        scope = category_scope(cat)
        kg = r.get("co2_kg", 0.0) or 0.0
        totals[scope]["total_co2_kg"] += kg
        totals[scope]["by_category"][cat] = totals[scope]["by_category"].get(cat, 0.0) + kg
    items = []
    for scope in SCOPE_ORDER:
        item = totals[scope]
        item["total_co2_t"] = item["total_co2_kg"] / 1000.0
        items.append(item)
    return items
