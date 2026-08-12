#!/usr/bin/env python3
"""Apply the emission-factor reconciliation decided for the 2026-08 PoC.

Adds versioned factor rows (effective_from=2026-08-12) for values confirmed
against primary sources, and refreshes source descriptions on unchanged rows.
No existing factor row is deleted and no value is changed in place; new rows
supersede old ones for calculations on/after their effective date.

Usage:
  python scripts/reconcile_emission_factors.py            # dry-run
  python scripts/reconcile_emission_factors.py --apply    # commit changes
"""
import argparse
import datetime
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models  # noqa: E402
from app.crud import utcnow  # noqa: E402
from app.database import SessionLocal, create_tables  # noqa: E402
from seed_data import FACTORS  # noqa: E402


def _key(f):
    return (
        f["category"],
        f["item_name"],
        f["unit"],
        f.get("supplier"),
        datetime.date.fromisoformat(f["effective_from"]),
    )


def reconcile(apply: bool) -> None:
    create_tables()
    db = SessionLocal()
    planned_adds = 0
    planned_updates = 0
    conflicts = 0
    actor = "system:factor-reconcile"

    for f in FACTORS:
        category, item_name, unit, supplier, effective_from = _key(f)
        query = db.query(models.EmissionFactor).filter(
            models.EmissionFactor.category == category,
            models.EmissionFactor.item_name == item_name,
            models.EmissionFactor.unit == unit,
            models.EmissionFactor.effective_from == effective_from,
        )
        if supplier:
            query = query.filter(models.EmissionFactor.supplier == supplier)
        else:
            query = query.filter(models.EmissionFactor.supplier.is_(None))
        existing = query.first()

        if existing:
            if existing.factor_value != f["factor_value"]:
                print(
                    f"CONFLICT {category}/{item_name} "
                    f"({effective_from}, supplier={supplier}): "
                    f"db={existing.factor_value} seed={f['factor_value']}"
                )
                conflicts += 1
                continue
            if existing.source != f["source"]:
                planned_updates += 1
                print(
                    f"UPDATE {category}/{item_name} "
                    f"({effective_from}, supplier={supplier}): source updated"
                )
                if apply:
                    existing.source = f["source"]
                    existing.updated_at = utcnow()
                    existing.updated_by = actor
                    db.add(
                        models.AuditLog(
                            log_id=str(uuid.uuid4()),
                            actor=actor,
                            action="update",
                            resource_type="factor",
                            resource_id=existing.factor_id,
                            detail=f"source: {f['source'][:200]}",
                            created_at=utcnow(),
                        )
                    )
            continue

        planned_adds += 1
        print(
            f"ADD {category}/{item_name} "
            f"({effective_from}, supplier={supplier}, value={f['factor_value']})"
        )
        if apply:
            now = utcnow()
            factor = models.EmissionFactor(
                factor_id=str(uuid.uuid4()),
                category=category,
                item_name=item_name,
                unit=unit,
                factor_value=f["factor_value"],
                effective_from=effective_from,
                source=f["source"],
                supplier=supplier,
                created_at=now,
                created_by=actor,
            )
            db.add(factor)
            db.flush()
            db.add(
                models.AuditLog(
                    log_id=str(uuid.uuid4()),
                    actor=actor,
                    action="create",
                    resource_type="factor",
                    resource_id=factor.factor_id,
                    detail=(
                        f"{category}/{item_name} {f['factor_value']} "
                        f"from {effective_from} (supplier={supplier})"
                    ),
                    created_at=now,
                )
            )

    if apply:
        db.commit()
        mode = "APPLIED"
    else:
        db.rollback()
        mode = "DRY-RUN"

    db.close()
    print(
        f"[{mode}] adds={planned_adds} source_updates={planned_updates} "
        f"conflicts={conflicts}"
    )
    if conflicts:
        sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit changes (default is dry-run)",
    )
    args = parser.parse_args()
    reconcile(apply=args.apply)


if __name__ == "__main__":
    main()
