"""The answer key for a whole run.

One invoice on its own proves little. What the cost desk is actually asked
is: what did it cost to land this part in Louveira? That needs the order,
the goods invoice, the shipment, and every freight invoice against it.

This module writes that chain down, so whatever reads the mailbox later can
be scored against it.
"""

from decimal import Decimal

from drawing import scan

ZERO = Decimal('0.00')


def build(operation):
    """The whole run, as plain data."""
    from datetime import timedelta
    return {
        'period': {
            'start': operation.start.isoformat(),
            'until': (operation.last_day - timedelta(days=1)).isoformat(),
        },
        'orders': [_order(order) for order in operation.orders],
        'shipments': [_shipment(ship) for ship in operation.shipments],
        'invoices': [dict(invoice.as_truth(), scanned=scan.chosen(invoice.number))
                     for invoice in operation.invoices],
        'chains': chains(operation),
        'counts': counts(operation),
    }


def chains(operation):
    """Order, goods invoice, shipment, freight, and the landed cost.

    A container carries more than one order, so its freight is split
    between them by how much of the cargo value each one is. Charging the
    whole container to every order it touched would count it twice.
    """
    owed = payable(operation)
    cargo_value = _cargo_value_by_shipment(owed)

    built = []
    for order in operation.orders:
        goods = [i for i in owed
                 if i.kind == 'goods' and i.order_number == order.number]
        if not goods:
            continue
        shipment_ids = {i.shipment_id for i in goods}
        # The landed cost here is in dollars; the reais documents of the
        # Brazilian side are costed by costing.py, at the declaration's rate.
        freight = [i for i in owed
                   if i.kind == 'freight' and i.currency == 'USD'
                   and i.shipment_id in shipment_ids]
        # A credit names the invoice it credits; that invoice may since
        # have been revised, and the order keeps only the revision.
        credited = ({g.number for g in goods}
                    | {g.revises for g in goods if g.revises})
        credits = [i for i in operation.invoices
                   if i.kind == 'credit' and i.revises in credited]

        goods_total = sum((i.grand_total for i in goods), ZERO)
        credit_total = sum((i.grand_total for i in credits), ZERO)
        freight_total, shares = _apportioned_freight(
            goods, freight, cargo_value)

        built.append({
            'order_number': order.number,
            'factory': order.factory_code,
            'raised_on': order.raised_on.isoformat(),
            'ordered_value': str(order.value),
            'goods_invoices': [i.number for i in goods],
            'shipments': sorted(shipment_ids),
            'freight_invoices': [i.number for i in freight],
            'freight_share': shares,
            'credit_notes': [i.number for i in credits],
            'goods_total': str(goods_total),
            'freight_total': str(freight_total),
            'credit_total': str(credit_total),
            'landed_cost': str(goods_total + freight_total + credit_total),
            'fully_shipped': _fully_shipped(order, operation),
        })
    return built


def _cargo_value_by_shipment(payable):
    """What the goods on each shipment were worth in total."""
    totals = {}
    for invoice in payable:
        if invoice.kind != 'goods' or not invoice.shipment_id:
            continue
        totals[invoice.shipment_id] = (
            totals.get(invoice.shipment_id, ZERO) + invoice.grand_total)
    return totals


def _apportioned_freight(goods, freight, cargo_value):
    """This order's slice of every freight invoice against its shipments."""
    mine = {}
    for invoice in goods:
        mine[invoice.shipment_id] = (
            mine.get(invoice.shipment_id, ZERO) + invoice.grand_total)

    total = ZERO
    shares = {}
    for invoice in freight:
        whole = cargo_value.get(invoice.shipment_id, ZERO)
        share = (mine.get(invoice.shipment_id, ZERO) / whole) if whole else 1
        slice_ = Decimal(f'{invoice.grand_total * Decimal(share):.2f}')
        shares[invoice.number] = str(slice_)
        total += slice_
    return Decimal(f'{total:.2f}'), shares


def counts(operation):
    kinds = {}
    for invoice in operation.invoices:
        kinds[invoice.kind] = kinds.get(invoice.kind, 0) + 1
    numbers = [i.number for i in operation.invoices]
    return {
        'orders': len(operation.orders),
        'shipments': len(operation.shipments),
        'invoices': len(operation.invoices),
        'by_kind': kinds,
        'duplicate_numbers': len(numbers) - len(set(numbers)),
        'revisions': len([i for i in operation.invoices
                          if i.number.endswith('-R1')]),
        'wrong_order_quoted': len([
            i for i in operation.invoices
            if i.kind == 'goods' and i.reference != i.order_number
        ]),
    }


def payable(operation):
    """Every document that is actually owed.

    Two kinds are dropped. The invoice a revision replaces, because the
    revision is what is owed. And the second copy of a resend, because a
    resend is the same debt arriving twice.

    Identity here is the object, not the number and not equality. A
    resend is an exact copy, so `==` says the two are the same thing and
    `list.index` returns the first for both. Only `is` can tell them
    apart, which is why this walks the list once and remembers what it
    has already kept.
    """
    revised = {invoice.revises for invoice in operation.invoices
               if invoice.number.endswith('-R1')}

    kept = []
    seen_numbers = set()
    for invoice in operation.invoices:
        if invoice.number in revised:
            continue
        if invoice.number in seen_numbers:
            continue
        seen_numbers.add(invoice.number)
        kept.append(invoice)
    return kept


def _fully_shipped(order, operation):
    wanted = {line.code: line.quantity for line in order.lines}
    sent = {}
    for dispatch in operation.dispatches:
        if dispatch.order_number != order.number:
            continue
        for part, quantity in dispatch.lines:
            sent[part.code] = sent.get(part.code, 0) + quantity
    return all(sent.get(code, 0) >= quantity
               for code, quantity in wanted.items())


def _order(order):
    return {
        'number': order.number,
        'factory': order.factory_code,
        'raised_on': order.raised_on.isoformat(),
        'required_by': order.required_by.isoformat(),
        'value': str(order.value),
        'lines': [
            {'code': line.code, 'quantity': line.quantity,
             'agreed_price': str(line.agreed_price)}
            for line in order.lines
        ],
    }


def _shipment(ship):
    return {
        'identifier': ship.identifier,
        'factory': ship.factory_code,
        'carrier': ship.carrier_code,
        'mode': ship.mode,
        'departed_on': ship.departed_on.isoformat(),
        'arrived_on': ship.arrived_on.isoformat(),
        'transit_days': ship.transit_days,
        'origin': ship.origin,
        'load': ship.load,
        'container': ship.container,
        'weight_kg': str(ship.weight_kg),
        'volume_m3': str(ship.volume_m3),
        'covers': ship.covers,
    }
