"""Benchmark comparison and anomaly detection for emissions data."""
import statistics
from datetime import date

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

    history_months = _months_before(target_month, 5)
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
        recent_hist = hist[:3]
        if len(recent_hist) >= 2:
            avg = sum(recent_hist) / len(recent_hist)
            if avg > 0:
                ratio = a.quantity / avg
                if ratio >= threshold_high:
                    reasons.append(f"直近3ヶ月平均比 {ratio:.1f}倍（平均 {avg:,.3f}{a.unit}）")
                elif ratio <= threshold_low:
                    reasons.append(f"直近3ヶ月平均比 {ratio:.1%}（平均 {avg:,.3f}{a.unit}）")
        if len(hist) >= 5:
            mean = statistics.mean(hist)
            stdev = statistics.stdev(hist)
            if stdev > 0:
                z = (a.quantity - mean) / stdev
                if abs(z) >= 2.5:
                    reasons.append(
                        f"Zスコア {z:.1f}（過去{len(hist)}ヶ月: 平均 {mean:,.3f} / σ {stdev:,.3f}{a.unit}）"
                    )
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


def get_comparison(db: Session, project_id: str, target_month: str) -> dict:
    current = sum(
        r.co2_kg for r in crud.get_results_by_project(
            db, project_id=project_id, target_month=target_month
        )
    )
    previous_month = _previous_month(target_month)
    prev_month_kg = sum(
        r.co2_kg for r in crud.get_results_by_project(
            db, project_id=project_id, target_month=previous_month
        )
    )
    year, month = (int(x) for x in target_month.split("-"))
    previous_year = f"{year - 1}-{month:02d}"
    prev_year_kg = sum(
        r.co2_kg for r in crud.get_results_by_project(
            db, project_id=project_id, target_month=previous_year
        )
    )
    return {
        "current_total_kg": current,
        "current_total_t": current / 1000.0,
        "previous_month_kg": prev_month_kg or None,
        "previous_month_t": prev_month_kg / 1000.0 if prev_month_kg else None,
        "mom_ratio": current / prev_month_kg if prev_month_kg else None,
        "previous_year_kg": prev_year_kg or None,
        "previous_year_t": prev_year_kg / 1000.0 if prev_year_kg else None,
        "yoy_ratio": current / prev_year_kg if prev_year_kg else None,
    }


def get_missing_months(db: Session, project_id: str) -> list[dict]:

    project = crud.get_project(db, project_id)
    if not project:
        return []
    start = project.start_date or date.today().replace(day=1)
    end = min(project.end_date or date.today(), date.today())
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        month = f"{y}-{m:02d}"
        activities = crud.list_activity_data(
            db, project_id=project_id, target_month=month
        )
        if not activities:
            months.append({"target_month": month, "activity_count": 0, "reason": "no_data"})
        else:
            unapproved = [a for a in activities if not a.approved]
            if unapproved:
                months.append({
                    "target_month": month,
                    "activity_count": len(unapproved),
                    "reason": "unapproved",
                })
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


def forecast_next_month(db: Session, project_id: str) -> dict:
    trend = crud.get_monthly_trend(db, project_id=project_id)
    points = [(i, t["total_co2_kg"]) for i, t in enumerate(sorted(trend, key=lambda x: x["target_month"]))]
    if len(points) < 2:
        return {
            "target_month": "",
            "forecast_total_kg": 0.0,
            "forecast_total_t": 0.0,
            "trend_slope_kg_per_month": 0.0,
        }
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    n = len(points)
    slope = (n * sum(x * y for x, y in zip(xs, ys, strict=True)) - sum(xs) * sum(ys)) / (
        n * sum(x * x for x in xs) - sum(xs) ** 2
    )
    intercept = (sum(ys) - slope * sum(xs)) / n
    next_index = xs[-1] + 1
    forecast_kg = max(0.0, intercept + slope * next_index)
    last_month = trend[-1]["target_month"]
    year, month = (int(x) for x in last_month.split("-"))
    next_month = f"{year}-{month + 1:02d}" if month < 12 else f"{year + 1}-01"
    return {
        "target_month": next_month,
        "forecast_total_kg": forecast_kg,
        "forecast_total_t": forecast_kg / 1000.0,
        "trend_slope_kg_per_month": slope,
    }


def simulate_scenario(
    db: Session, project_id: str, target_month: str | None, adjustments: dict
) -> dict:
    from .scope import category_scope

    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)
    current_by_category: dict[str, float] = {}
    for r in results:
        cat = r.activity.category
        current_by_category[cat] = current_by_category.get(cat, 0.0) + r.co2_kg

    current_total = sum(current_by_category.values())
    scenario_by_category: dict[str, dict] = {}
    scenario_total = 0.0
    for cat, kg in current_by_category.items():
        adj = float(adjustments.get(cat, 0.0) or 0.0)
        new_kg = max(0.0, kg * (1.0 + adj / 100.0))
        scenario_by_category[cat] = {
            "current_kg": kg,
            "scenario_kg": new_kg,
            "reduction_kg": kg - new_kg,
        }
        scenario_total += new_kg

    scope_after: dict[str, float] = {}
    for cat, data in scenario_by_category.items():
        scope = category_scope(cat)
        scope_after[scope] = scope_after.get(scope, 0.0) + data["scenario_kg"]
    reduction = current_total - scenario_total
    return {
        "current_total_kg": current_total,
        "scenario_total_kg": scenario_total,
        "reduction_kg": reduction,
        "reduction_t": reduction / 1000.0,
        "reduction_percent": reduction / current_total * 100.0 if current_total else 0.0,
        "by_category": scenario_by_category,
        "scope_after": scope_after,
    }
