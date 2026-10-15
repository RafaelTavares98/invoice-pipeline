"""What each issuer's page is made of: its columns, labels and page size."""

from dataclasses import dataclass

GOODS_COLUMNS = (
    ('Part no.', 'code'),
    ('Description of goods', 'description'),
    ('HS code', 'hs_code'),
    ('Qty', 'quantity'),
    ('Unit price', 'unit_price'),
    ('Amount USD', 'net'),
)

FREIGHT_COLUMNS = (
    ('Charge description', 'description'),
    ('Units', 'quantity'),
    ('Weight kg', 'weight'),
    ('Volume m3', 'volume'),
    ('Rate', 'unit_price'),
    ('Amount USD', 'net'),
)


#: The duty statement: each tax on its base, at its rate.
CUSTOMS_COLUMNS = (
    ('Description', 'description'),
    ('Base BRL', 'base'),
    ('Rate', 'unit_price'),
    ('Amount BRL', 'net'),
)

#: A service invoice: what was done, how many times, at what price.
SERVICE_COLUMNS = (
    ('Description', 'description'),
    ('Qty', 'quantity'),
    ('Unit price', 'unit_price'),
    ('Amount BRL', 'net'),
)


@dataclass(frozen=True)
class Layout:
    issuer: object
    columns: tuple
    title: str
    issued_label: str
    due_label: str
    landscape: bool
    number_label: str = 'Invoice no.'
    #: A carrier's Santos office bills local charges in reais, though the
    #: carrier itself bills in dollars.
    billed_in: str = ''

    @property
    def style(self):
        return self.issuer.style

    @property
    def accent(self):
        return self.issuer.accent

    @property
    def decimal_mark(self):
        return self.issuer.decimal_mark

    @property
    def date_order(self):
        return self.issuer.date_order

    @property
    def currency(self):
        return self.billed_in or self.issuer.currency


def layout_for(issuer, kind=''):
    if kind == 'local':
        return Layout(issuer=issuer, columns=SERVICE_COLUMNS,
                      title='Local charges', issued_label='Invoice date',
                      due_label='Due', landscape=False, billed_in='BRL')
    if issuer.kind == 'terminal':
        return Layout(issuer=issuer, columns=SERVICE_COLUMNS,
                      title='Storage invoice', issued_label='Invoice date',
                      due_label='Due', landscape=False)
    if kind == 'customs':
        return Layout(
            issuer=issuer,
            columns=CUSTOMS_COLUMNS,
            title='Import duty statement',
            issued_label='Registered',
            due_label='Due',
            landscape=False,
            number_label='Statement no.',
        )
    if issuer.kind == 'broker':
        return Layout(
            issuer=issuer,
            columns=SERVICE_COLUMNS,
            title='Service invoice',
            issued_label='Invoice date',
            due_label='Due',
            landscape=False,
        )
    if issuer.kind == 'carrier':
        return Layout(
            issuer=issuer,
            columns=FREIGHT_COLUMNS,
            title='Freight invoice',
            issued_label='Invoice date',
            due_label='Due',
            landscape=True,
        )

    return Layout(
        issuer=issuer,
        columns=GOODS_COLUMNS,
        title='Commercial invoice',
        issued_label='Date of issue',
        due_label='Payment due',
        landscape=False,
    )


def description_at(layout):
    for index, (_, held) in enumerate(layout.columns):
        if held == 'description':
            return index
    return 0
