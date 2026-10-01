import pytest
from app.tools import basic_calculator, calculate_tip, convert_units


def test_calculate_tip():
    res = calculate_tip(bill_amount=100.0, tip_percentage=20.0, split_by=4)
    assert res["tip_amount"] == 20.0
    assert res["total_amount"] == 120.0
    assert res["per_person"] == 30.0


def test_calculate_tip_invalid():
    assert "error" in calculate_tip(bill_amount=-10)
    assert "error" in calculate_tip(bill_amount=50, tip_percentage=-5)
    assert "error" in calculate_tip(bill_amount=50, split_by=0)


def test_convert_units_temperature():
    res = convert_units(value=100, from_unit="celsius", to_unit="fahrenheit")
    assert res["result_value"] == 212.0

    res2 = convert_units(value=32, from_unit="fahrenheit", to_unit="celsius")
    assert res2["result_value"] == 0.0


def test_convert_units_length():
    res = convert_units(value=1, from_unit="km", to_unit="meters")
    assert res["result_value"] == 1000.0


def test_basic_calculator():
    res = basic_calculator("multiply", 7, 8)
    assert res["result"] == 56

    res_div_zero = basic_calculator("divide", 10, 0)
    assert "error" in res_div_zero
