"""Who each sender is, in the project's story, and how it is simulated.

Written into the body of smoke test 2, so a reader sees what every sender
makes or moves, how it sells, and how the simulation keeps its documents
believable. Everything here is invented.
"""

from business import catalogue

#: One line per sender: who it is in the story.
LORE = {
    'NCL': 'A closures and pumps plant in Ningbo; steady prices a little '
           'under the catalogue, shipped from Ningbo port.',
    'SBP': 'A carton and label printer in Shantou; cheap, and the quickest '
           'to deliver.',
    'GZV': 'A glassworks in Guangzhou making bottles and jars; heavy cargo, '
           'the longest lead time, totals printed on top of the page.',
    'HCV': 'A Korean maker of pumps and jars, dearer and very consistent; '
           'it sells CIF Santos, so its price already carries the ocean freight.',
    'BDT': 'A tube and closure works in Binh Duong, Vietnam; cheap but '
           'uneven prices, and large orders it sometimes ships in parts.',
    'ARL': 'A label and carton printer near Mumbai; cheap and erratic, '
           'writes amounts as 1.234,56.',
    'DHI': 'A Hong Kong forwarder: it consolidates small shipments into shared '
           'containers (LCL) and flies the late ones; its Santos office bills '
           'the local charges in reais.',
    'MRK': 'A container line: full containers (FCL) from Asia to Santos under '
           'a yearly service contract; its Santos office bills the local charges.',
    'CSM': 'A second container line, also FCL, used when Marsk has no space; '
           'its Santos office bills the local charges.',
    'KNG': 'A logistics group that hauls containers by road and rents Moty a '
           'bonded warehouse bay by the month.',
    'TLV': 'The truck company that takes every shipment from Santos up to the '
           'plant in Louveira, billed in reais.',
    'SCA': 'The customs broker in Santos: it registers each import, sends the '
           'duty statement, and bills its own fees under a contract.',
    'TVA': 'The bonded terminal in Santos where cargo waits for clearance; it '
           'bills storage as a share of the goods\' CIF value.',
}

NEWCOMER_LORE = {
    'unmatched': 'A company entered in the vendor master with no purchase '
                 'order behind it. It bills round sums for vague services.',
    'supplier': 'A new factory that won business this year. It has an order, '
                'and its goods arrive like anyone else\'s.',
}

CAVEAT = ('Invented for the invoice pipeline project. The sender, its '
          'documents and every figure are simulated; none is real.')


def describe(issuer, documents, newcomer=''):
    """The body of one sender's mail in smoke test 2."""
    lore = NEWCOMER_LORE.get(newcomer) or LORE[issuer.code]
    listed = '\n'.join(f'- {name}: {what}' for name, what in documents)
    return (
        f'{issuer.name}\n\n'
        f'What it does\n{lore}\n\n'
        f'How it sells\n{_sells(issuer, newcomer)}\n\n'
        f'How the simulation draws it\n{_drawn(issuer, newcomer)}'
        f'{_scans(issuer)}\n\n'
        f'In this mail\n{listed}\n\n'
        f'{CAVEAT}\n'
    )


def _scans(issuer):
    """The issuer's scanning habit, when it has one."""
    from drawing import scan
    habit = scan.HABITS.get(issuer.code)
    if habit is None:
        return ''
    grade = scan.QUALITIES[habit.quality]
    laid = (f', {habit.askew:.0%} of those laid up to 15 degrees askew'
            if habit.askew else ', always straight')
    colour = 'black and white' if grade.black_and_white else 'grey'
    return (f' It prints, signs and scans {habit.share:.0%} of its invoices: '
            f'{colour} at {grade.dpi} dpi{laid}.')


def _sells(issuer, newcomer):
    if newcomer == 'unmatched':
        return 'No contract and no order; bills of US$3,000 to US$12,000.'
    if issuer.kind == 'factory':
        families = ', '.join(sorted(set(issuer.families)))
        return (f'Sells {families}, {issuer.incoterm}, in US dollars. '
                f'Terms: {issuer.terms}')
    return f'{issuer.terms} Bills in {issuer.currency}.'


def _drawn(issuer, newcomer):
    if newcomer == 'unmatched':
        return 'Three to six bills over a few months, each a round hundred.'
    if issuer.kind == 'factory':
        parts = [p for p in catalogue.CATALOGUE if p.family in issuer.families]
        low = min(p.base_price for p in parts)
        high = max(p.base_price for p in parts)
        return (f'Unit prices are drawn around the catalogue price '
                f'(US${low:.3f} to US${high:.3f} a unit for its parts), times '
                f'{issuer.price_bias:.2f} for this supplier, spread '
                f'{issuer.price_spread:.0%}, less volume discounts. Lead time '
                f'{issuer.lead_days} days plus a slip of 0 to 14.')
    if issuer.code in ('MRK', 'CSM'):
        return ('FCL at US$4,250 a 20\' and US$5,800 a 40\', 2026 levels; '
                'capatazia R$3,700 a container and B/L release R$1,000 in Santos.')
    if issuer.code == 'DHI':
        return ('LCL at US$95 per W/M (m3 or tonnes, whichever is greater); air '
                'at US$8.60 per chargeable kg (kg or m3 x 167); capatazia R$80 '
                'per W/M, minimum R$150, and B/L release R$1,000.')
    if issuer.code == 'KNG':
        return 'Road haulage per trip with its surcharges; a fixed monthly rent.'
    if issuer.code == 'TLV':
        return ('About R$3,900 a truck, drawn within 10%, plus toll and cargo '
                'insurance at 0.3% of the goods.')
    if issuer.code == 'SCA':
        return ('Duties from the tariff of each part\'s NCM; fees from its '
                'contract: clearance R$1,450, documents R$180, handling R$1,150.')
    if issuer.code == 'TVA':
        return ('First period: FCL 0.48% of CIF, at least R$1,466.88 a 20\' or '
                'R$1,881.43 a 40\'; LCL 1.16% of CIF.')
    return 'Drawn from its own rate card.'
