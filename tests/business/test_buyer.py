"""Who receives the invoices: a cost team, not a payments team."""

from pathlib import Path

from business.buyer import MOTY

README = Path(__file__).resolve().parents[2] / 'README.md'


def test_the_department_manages_costs():
    assert MOTY.department == 'Production and Logistics Cost Management'


def test_the_story_says_the_department_does_not_pay():
    text = README.read_text(encoding='utf-8')

    assert 'does not pay invoices' in text
    assert 'Production and Logistics Cost Management' in text
