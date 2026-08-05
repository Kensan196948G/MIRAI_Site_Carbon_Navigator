"""Benchmark comparison and anomaly detection for emissions data."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from .. import crud, models


def _previous_month(target_month: str) -> str:
    year, month = (int(x) for x in target_month.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _months_before(target_month: str, count: int) -> list[str]:
    year, month = (int(x) for x in target_month.split("-"))
    months = []
    for i in range(1, count + 1):
        m = month - i
        y = year
        while m < 1:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}")
    return months


def get_benchmark(
    db: Session, project: models.Project, target_month: str
) -> dict:
    """Compare a project's monthly emissions with other projects of same work_type."""
    current_results = crud.get_results_by_project(
        db, project_id=project.project_id, target_month=target_month
    )
    current_total_kg = sum(r.co2_kg for r in current_results)
    current_by_category: dict[str, float] = {}
    for r in current_results:
        cat = r.activity.category
        current_by_category[cat] = current_by_category.get(cat, 0.0) + r.co2_kg

    peers = [
        p for p in crud.list_projects(db)
        if p.project_id != project.project_id and p.work_type == project.work_type
    ]
    peer_totals: list[float] = []
    peer_category: dict[str, float] = {}
    peer_month_count = 0
    for peer in peers:
        for r in crud.get_results_by_project(db, project_id=peer.project_id):
            peer_totals.append(r.co2_kg)
            cat = r.activity.category
            peer_category[cat] = peer_category.get(cat, 0.0) + r.co2_kg
        # count months with any result
        months = {r.activity.target_month for r in crud.get_results_by_project(db, project_id=peer.project_id)}
        peer_month_count += len(months)

    peer_avg_monthly_kg = None
    peer_avg_monthly_t = None
    peer_project_count = len(peers)
    if peer_totals and peer_month_count:
        peer_avg_monthly_kg = sum(peer_totals) / peer_month_count
        peer_avg_monthly_t = peer_avg_monthly_kg / 1000.0

    comparison_ratio = None
    if peer_avg_monthly_kg and peer_avg_monthly_kg > 0:
        comparison_ratio = current_total_kg / peer_avg_monthly_kg

    return {
        "project_id": project.project_id,
        "target_month": target_month,
        "work_type": project.work_type,
        "current_total_kg": current_total_kg,
        "current_total_t": current_total_kg / 1000.0,
        "current_by_category": current_by_category,
        "peer_project_count": peer_project_count,
        "peer_avg_monthly_kg": peer_avg_monthly_kg,
        "peer_avg_monthly_t": peer_avg_monthly_t,
        "peer_by_category": peer_category,
        "comparison_ratio": comparison_ratio,
    }


def detect_anomalies(
    db: Session, project_id: str, target_month: str, threshold_high: float = 2.0, threshold_low: float = 0.5
) -> list[dict]:
    """Detect activity quantities that deviate from previous month / 3-month average."""
    activities = crud.list_activity_data(
        db, project_id=project_id, target_month=target_month, approved=True
    )
    previous = crud.list_activity_data(
        db, project_id=project_id, target_month=_previous_month(target_month), approved=True
    )
    previous_by_key = {
        (a.category, a.item_name, a.unit): a.quantity for a in previous
    }

    history_months = _months_before(target_month, 3)
    history: dict[tuple, list[float]] = {}
    for m in history_months:
        for a in crud.list_activity_data(db, project_id=project_id, target_month=m, approved=True):
            key = (a.category, a.item_name, a.unit)
            history.setdefault(key, []).append(a.quantity)

    anomalies: list[dict] = []
    for a in activities:
        key = (a.category, a.item_name, a.unit)
        reasons: list[str] = []
        prev_qty = previous_by_key.get(key)
        if prev_qty and prev_qty > 0:
            ratio = a.quantity / prev_qty
            if ratio >= threshold_high:
                reasons.append(f"前月比 {ratio:.1f}倍（前月 {prev_qty:,.3f}{a.unit}）")
            elif ratio <= threshold_low:
                reasons.append(f"前月比 {ratio:.1%}（前月 {prev_qty:,.3f}{a.unit}）")
        hist = history.get(key, [])
        if len(hist) >= 2:
            avg = sum(hist) / len(hist)
            if avg > 0:
                ratio = a.quantity / avg
                if ratio >= threshold_high:
                    reasons.append(f"3ヶ月平均比 {ratio:.1f}倍（平均 {avg:,.3f}{a.unit}）")
                elif ratio <= threshold_low:
                    reasons.append(f"3ヶ月平均比 {ratio:.1%}（平均 {avg:,.3f}{a.unit}）")
        if reasons:
            anomalies.append({
                "activity_id": a.activity_id,
                "category": a.category,
                "item_name": a.item_name,
                "quantity": a.quantity,
                "unit": a.unit,
                "reasons": reasons,
            })
    return anomalies
