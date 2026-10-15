"""The operational targets, computed from what the reader filed.

The close is the 6th business day of the next month. A cost is known
before the close when every document behind it was registered by then.
"""

from datetime import date
from decimal import Decimal

from costing import kpis


def row(number, arrived, registered, problems='', status='new', kind='goods',
        shipment='S1', issued='2026-04-06'):
    return {'invoice_number': number, 'first_seen': arrived,
            'registered_at': registered, 'problems': problems,
            'status': status, 'kind': kind, 'shipment_id': shipment,
            'issue_date': issued, 'currency': 'USD'}


class TestTheClose:
    def test_the_sixth_business_day_of_the_next_month(self):
        # May 2026 opens on a Friday: 1, 4, 5, 6, 7, 8.
        assert kpis.close_day(2026, 4) == date(2026, 5, 8)

    def test_december_closes_in_january(self):
        assert kpis.close_day(2026, 12).year == 2027


class TestSameDay:
    def test_the_share_registered_the_day_it_arrived(self):
        rows = [row('A', '2026-04-06T09:00:00-03:00', '2026-04-06T09:01:00-03:00'),
                row('B', '2026-04-06T09:00:00-03:00', '2026-04-07T10:00:00-03:00')]

        assert kpis.analysed_same_day(rows) == Decimal('50.0')

    def test_the_day_is_brasilias_not_utc(self):
        """22:30 in Brasilia is past midnight UTC, and still the same day."""
        rows = [row('A', '2026-04-06T22:00:00-03:00', '2026-04-07T01:30:00+00:00')]

        assert kpis.analysed_same_day(rows) == Decimal('100.0')


class TestOurErrors:
    def test_a_problem_or_an_unreadable_file_is_ours(self):
        rows = [row('A', '', '', problems='no total'),
                row('B', '', '', status='unreadable'),
                row('C', '', '')]
        found = kpis.exceptions(rows)

        assert [(e['invoice_number'], e['origin']) for e in found] == [
            ('A', 'ours'), ('B', 'ours')]
        assert kpis.our_error_rate(rows) == Decimal('66.7')


class TestBeforeTheClose:
    def test_a_cost_is_known_when_its_documents_are_in_by_the_close(self):
        rows = [row('G1', '', '2026-04-06T09:00:00-03:00', shipment='S1'),
                row('C1', '', '2026-05-20T09:00:00-03:00', kind='customs',
                    shipment='S1', issued='2026-05-20'),
                row('G2', '', '2026-04-10T09:00:00-03:00', shipment='S2')]
        cost = [{'shipment_id': 'S1', 'landed_brl': Decimal('300')},
                {'shipment_id': 'S2', 'landed_brl': Decimal('100')}]
        groups = {'S1': rows[:2], 'S2': rows[2:]}

        # The April close is 8 May: S1's statement came after it.
        assert kpis.known_before_close(cost, groups, 2026, 4) == Decimal('25.0')

    def test_goods_tied_by_the_dock_receipt_count_in_their_shipment(self):
        """A goods row whose page names no B/L still belongs to the
        shipment the receipts tie it to: the groups come from the cost
        report, not from the row."""
        goods = row('G1', '', '2026-04-06T09:00:00-03:00', shipment='')
        cost = [{'shipment_id': 'S1', 'landed_brl': Decimal('300')}]

        assert kpis.known_before_close(cost, {'S1': [goods]}, 2026, 4) == \
            Decimal('100.0')
