"""AI-style reduction assistant using historical performance and benchmarks."""
from sqlalchemy.orm import Session

from .. import crud
from .reduction import REDUCTION_RULES


def assistant_suggestions(db: Session, project, target_month: str) -> list[dict]:
    results = crud.get_results_by_project(
        db, project_id=project.project_id, target_month=target_month
    )
    totals: dict[str, float] = {}
    for r in results:
        cat = r.activity.category
        totals[cat] = totals.get(cat, 0.0) + r.co2_kg
    if not totals:
        return []

    # Peer history of implemented reduction actions (same work_type)
    peers = [
        p for p in crud.list_projects(db)
        if p.project_id != project.project_id and p.work_type == project.work_type
    ]
    peer_actions: dict[str, list[dict]] = {}
    for peer in peers:
        for action in crud.list_reduction_actions(db, project_id=peer.project_id):
            peer_actions.setdefault(action.category, []).append({
                "status": action.status,
                "estimated": action.estimated_reduction_kg,
                "actual": action.actual_reduction_kg,
            })

    # Peer category share (benchmark context)
    peer_category_kg: dict[str, float] = {}
    for peer in peers:
        for r in crud.get_results_by_project(db, project_id=peer.project_id):
            cat = r.activity.category
            peer_category_kg[cat] = peer_category_kg.get(cat, 0.0) + r.co2_kg
    peer_total = sum(peer_category_kg.values())
    peer_share = {
        cat: kg / peer_total if peer_total else 0.0
        for cat, kg in peer_category_kg.items()
    }
    project_total = sum(totals.values())
    project_share = {
        cat: kg / project_total if project_total else 0.0
        for cat, kg in totals.items()
    }

    suggestions = []
    for cat, _kg in sorted(totals.items(), key=lambda x: -x[1])[:4]:
        evidence = peer_actions.get(cat, [])
        implemented = [a for a in evidence if a["status"] == "implemented"]
        avg_actual = None
        if implemented:
            values = [a["actual"] for a in implemented if a.get("actual")]
            avg_actual = sum(values) / len(values) if values else None
        confidence = min(0.95, 0.4 + 0.1 * len(evidence))
        rationale_parts = []
        if implemented:
            rationale_parts.append(
                f"同工種の他工事で「{cat}」の削減アクション実績 {len(implemented)} 件"
            )
        share_ratio = (
            project_share.get(cat, 0.0) / peer_share.get(cat, 0.0)
            if peer_share.get(cat, 0.0)
            else None
        )
        if share_ratio and share_ratio > 1.2:
            rationale_parts.append(
                f"同工種平均と比べて排出割合が {share_ratio:.1f} 倍と高い"
            )
        if not rationale_parts:
            rationale_parts.append("排出量上位カテゴリ")
        suggestions.append({
            "category": cat,
            "title": f"{cat} の削減施策（上位カテゴリ）",
            "rationale": "、".join(rationale_parts),
            "actions": (REDUCTION_RULES.get(cat) or ["削減の取り組みを検討"])[:3],
            "confidence": round(confidence, 2),
            "estimated_reduction_kg": avg_actual,
        })
    return suggestions
