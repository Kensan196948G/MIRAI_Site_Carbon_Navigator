from .. import models

REDUCTION_RULES = {
    "fuel": [
        "待機時間削減による燃料消費低減",
        "工程再配置による機械稼働率最適化",
        "海象・気象予測活用による船舶待機削減",
        "低燃費建設機械・船舶への切り替え",
    ],
    "transport": [
        "積載率改善による輸送回数削減",
        "近隣調達による輸送距離短縮",
        "共同配送・混載による効率化",
        "輸送ルート最適化",
    ],
    "material": [
        "低炭素材料・エコセメントへの切り替え",
        "再生材・リサイクル材の活用",
        "設計数量見直しによる材料使用量削減",
        "プレキャスト工法による現場打設コンクリート削減",
    ],
    "power": [
        "再生可能エネルギー電力の調達",
        "仮設電源計画の見直し・省エネ機器採用",
        "LED照明・高効率機器への更新",
        "太陽光発電システムの現場導入",
    ],
}


def get_reduction_suggestions(results_with_category: list[dict]) -> list[dict]:
    """
    results_with_category: list of {"category": str, "co2_kg": float, ...}
    Returns top categories with reduction suggestions, ranked by total CO2.
    """
    # Aggregate by category
    totals: dict[str, float] = {}
    for r in results_with_category:
        cat = r.get("category", "other")
        totals[cat] = totals.get(cat, 0.0) + r.get("co2_kg", 0.0)

    # Sort by total CO2 descending
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    suggestions = []
    for rank, (category, total_co2) in enumerate(ranked, start=1):
        rules = REDUCTION_RULES.get(category, ["排出量削減の取り組みを検討してください"])
        suggestions.append({
            "category": category,
            "total_co2_kg": total_co2,
            "rank": rank,
            "suggestions": rules,
        })
    return suggestions
