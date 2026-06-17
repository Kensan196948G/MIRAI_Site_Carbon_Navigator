"""
Unit tests for the CO2 calculation service (app/services/calculator.py).
Tests the calculate_emissions() function directly against mock ORM objects.

SQLAlchemy ORM models cannot be safely instantiated with __new__ without a
bound session (instrumented attributes raise AttributeError). We use plain
SimpleNamespace objects that duck-type the same attributes the calculator
needs (category, item_name, unit, quantity, factor_value, effective_from).
"""
import datetime
from types import SimpleNamespace
import pytest

from app.services.calculator import calculate_emissions


# ---------------------------------------------------------------------------
# Helpers to build lightweight duck-typed model instances
# ---------------------------------------------------------------------------

def _factor(category, item_name, unit, factor_value, effective_from="2025-01-01"):
    return SimpleNamespace(
        factor_id="test-factor-id",
        category=category,
        item_name=item_name,
        unit=unit,
        factor_value=factor_value,
        effective_from=datetime.date.fromisoformat(effective_from),
        source="テスト用",
    )


def _activity(category, item_name, unit, quantity):
    return SimpleNamespace(
        activity_id="test-activity-id",
        category=category,
        item_name=item_name,
        unit=unit,
        quantity=quantity,
        project_id="proj-001",
        target_month="2026-05",
        approved=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCalculateEmissions:
    def test_calculate_co2_fuel(self):
        """500 L の軽油 × 2.58 kg-CO2/L = 1290.0 kg-CO2"""
        activity = _activity("fuel", "軽油", "L", 500.0)
        factors = [_factor("fuel", "軽油", "L", 2.58)]

        result = calculate_emissions(activity, factors)

        assert result == pytest.approx(1290.0)

    def test_calculate_co2_power(self):
        """1200 kWh × 0.434 kg-CO2/kWh = 520.8 kg-CO2"""
        activity = _activity("power", "電力", "kWh", 1200.0)
        factors = [_factor("power", "電力", "kWh", 0.434)]

        result = calculate_emissions(activity, factors)

        assert result == pytest.approx(520.8)

    def test_calculate_co2_material_kg(self):
        """コンクリート 5000 kg × 0.2 kg-CO2/kg = 1000.0 kg-CO2"""
        activity = _activity("material", "生コンクリート", "kg", 5000.0)
        factors = [_factor("material", "生コンクリート", "kg", 0.2)]

        result = calculate_emissions(activity, factors)

        assert result == pytest.approx(1000.0)

    def test_calculate_co2_material_tonne(self):
        """10 t × 2000 kg-CO2/t = 20000.0 kg-CO2"""
        activity = _activity("material", "鉄鋼材料", "t", 10.0)
        factors = [_factor("material", "鉄鋼材料", "t", 2000.0)]

        result = calculate_emissions(activity, factors)

        assert result == pytest.approx(20000.0)

    def test_calculate_no_matching_factor(self):
        """一致する排出係数がない場合は None を返す"""
        activity = _activity("fuel", "A重油", "L", 100.0)
        # 異なる item_name のファクターのみ提供
        factors = [_factor("fuel", "軽油", "L", 2.58)]

        result = calculate_emissions(activity, factors)

        assert result is None

    def test_calculate_no_factors_at_all(self):
        """ファクターリストが空の場合も None を返す"""
        activity = _activity("fuel", "軽油", "L", 100.0)

        result = calculate_emissions(activity, [])

        assert result is None

    def test_calculate_no_matching_category(self):
        """カテゴリが一致しない場合は None を返す"""
        activity = _activity("power", "電力", "kWh", 100.0)
        factors = [_factor("fuel", "電力", "kWh", 0.434)]

        result = calculate_emissions(activity, factors)

        assert result is None

    def test_calculate_no_matching_unit(self):
        """単位が一致しない場合は None を返す"""
        activity = _activity("fuel", "軽油", "L", 100.0)
        factors = [_factor("fuel", "軽油", "kL", 2580.0)]

        result = calculate_emissions(activity, factors)

        assert result is None

    def test_calculate_latest_factor(self):
        """同一品目に複数ファクターがある場合、effective_from が最新のものを使う"""
        activity = _activity("fuel", "軽油", "L", 100.0)
        old_factor = _factor("fuel", "軽油", "L", 2.50, effective_from="2020-01-01")
        new_factor = _factor("fuel", "軽油", "L", 2.58, effective_from="2025-04-01")
        factors = [old_factor, new_factor]

        result = calculate_emissions(activity, factors)

        # 最新の 2.58 を使用するはず
        assert result == pytest.approx(258.0)

    def test_calculate_latest_factor_reversed_order(self):
        """ファクターリストの順序に依存しないことを確認（古い順で渡しても最新を選ぶ）"""
        activity = _activity("fuel", "軽油", "L", 100.0)
        new_factor = _factor("fuel", "軽油", "L", 2.58, effective_from="2025-04-01")
        old_factor = _factor("fuel", "軽油", "L", 2.50, effective_from="2020-01-01")
        factors = [new_factor, old_factor]  # 新しい方を先に並べる

        result = calculate_emissions(activity, factors)

        assert result == pytest.approx(258.0)

    def test_calculate_zero_quantity(self):
        """数量ゼロは CO2 ゼロを返す"""
        activity = _activity("fuel", "軽油", "L", 0.0)
        factors = [_factor("fuel", "軽油", "L", 2.58)]

        result = calculate_emissions(activity, factors)

        assert result == pytest.approx(0.0)
