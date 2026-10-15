"""Who bills Moty.

Two kinds. A `Factory` sells components and bills for goods. A `Carrier`
moves them and bills for freight. The issuers abroad bill in US dollars; the
truck, the broker and the terminal in Santos bill in reais. What still
differs is the paperwork: the page design, the date order and the decimal
mark.
"""

from dataclasses import dataclass

CURRENCY = 'USD'


@dataclass(frozen=True)
class Issuer:
    code: str
    name: str
    address: tuple
    country: str
    tax_label: str
    tax_id: str
    terms: str
    bank_line: str
    style: str
    date_order: str
    decimal_mark: str
    number_prefix: str
    accent: tuple
    kind: str = 'factory'
    currency: str = CURRENCY


@dataclass(frozen=True)
class Factory(Issuer):
    families: tuple = ()
    price_bias: float = 1.0
    price_spread: float = 0.09
    incoterm: str = 'FOB'
    lead_days: int = 45
    tooling_chance: float = 0.12
    kind: str = 'factory'


@dataclass(frozen=True)
class Carrier(Issuer):
    mode: str = 'ocean'
    surcharges: tuple = ()
    price_bias: float = 1.0
    price_spread: float = 0.14
    kind: str = 'carrier'


INK = (0.12, 0.12, 0.12)

FACTORIES = (
    Factory(
        code='NCL',
        name='Ningbo Caplink Industrial Co., Ltd.',
        address=('No. 288 Jiangnan Road, Yinzhou District',
                 'Ningbo, Zhejiang 315100', 'China'),
        country='China',
        tax_label='USCC',
        tax_id='91330212MA2AF3K17H',
        terms='FOB Ningbo. T/T 30% deposit, balance against B/L copy.',
        bank_line='Bank of Ningbo  SWIFT BKNBCN2N  Acct 7801 4455 2190',
        style='grid',
        date_order='iso',
        decimal_mark='dot',
        number_prefix='NCL',
        accent=INK,
        families=('closure', 'pump'),
        price_bias=0.94,
        price_spread=0.07,
        lead_days=40,
    ),
    Factory(
        code='SBP',
        name='Shantou Brightpack Packaging Co., Ltd.',
        address=('Block C, Chenghai Industrial Park',
                 'Shantou, Guangdong 515800', 'China'),
        country='China',
        tax_label='USCC',
        tax_id='91440515MA4UQ8P23B',
        terms='FOB Shantou. Incoterms 2020. Settlement in USD.',
        bank_line='',
        style='zebra',
        date_order='iso',
        decimal_mark='dot',
        number_prefix='SBP',
        accent=(0.09, 0.32, 0.45),
        families=('carton', 'label'),
        price_bias=0.88,
        price_spread=0.11,
        lead_days=35,
        tooling_chance=0.22,
    ),
    Factory(
        code='GZV',
        name='Guangzhou Verrelia Glassworks Ltd.',
        address=('18 Xinsha Avenue, Huangpu District',
                 'Guangzhou, Guangdong 510700', 'China'),
        country='China',
        tax_label='Tax reg.',
        tax_id='91440112MA59WTQ84F',
        terms='FOB Nansha. All amounts in US dollars, net of Chinese VAT.',
        bank_line='ICBC Guangzhou  SWIFT ICBKCNBJGDX  Acct 3602 0012 9100',
        style='form',
        date_order='iso',
        decimal_mark='dot',
        number_prefix='GZV',
        accent=INK,
        families=('bottle', 'jar'),
        price_bias=1.06,
        price_spread=0.08,
        lead_days=55,
        tooling_chance=0.18,
    ),
    Factory(
        code='HCV',
        name='Hanil Cosmetic Vessels Co., Ltd.',
        address=('77 Namdong-daero, Namdong-gu',
                 'Incheon 21632', 'Republic of Korea'),
        country='Republic of Korea',
        tax_label='Business reg.',
        tax_id='131-86-40925',
        terms='CIF Santos. Payment at sight against documents.',
        bank_line='KEB Hana Bank  SWIFT KOEXKRSE  Acct 630-004188-712',
        style='minimal',
        date_order='month_first',
        decimal_mark='dot',
        number_prefix='HCV',
        accent=INK,
        families=('pump', 'jar'),
        price_bias=1.21,
        price_spread=0.06,
        incoterm='CIF',
        lead_days=50,
    ),
    Factory(
        code='BDT',
        name='Binh Duong Tubeworks JSC',
        address=('Lot G2, VSIP II Industrial Park',
                 'Thu Dau Mot, Binh Duong', 'Vietnam'),
        country='Vietnam',
        tax_label='Tax code',
        tax_id='3702145886',
        terms='FOB Cat Lai. 45 days from bill of lading date.',
        bank_line='',
        style='dashed',
        date_order='day_first',
        decimal_mark='dot',
        number_prefix='BDT',
        accent=(0.45, 0.17, 0.12),
        families=('tube', 'closure'),
        price_bias=0.91,
        price_spread=0.13,
        lead_days=38,
    ),
    Factory(
        code='ARL',
        name='Aravalli Labelworks Pvt. Ltd.',
        address=('Plot 42, Sector 8, IMT Manesar',
                 'Gurugram, Haryana 122051', 'India'),
        country='India',
        tax_label='GSTIN',
        tax_id='06AAFCA9321L1ZP',
        terms='FOB Nhava Sheva. Net 60. Artwork approval before print.',
        bank_line='HDFC Bank  SWIFT HDFCINBB  Acct 50200031947755',
        style='banded',
        date_order='day_first',
        decimal_mark='comma',
        number_prefix='ARL',
        accent=(0.10, 0.38, 0.26),
        families=('label', 'carton'),
        price_bias=0.83,
        price_spread=0.15,
        lead_days=42,
        tooling_chance=0.25,
    ),
)

CARRIERS = (
    Carrier(
        code='DHI',
        name='DHI Global Forwarding (HK) Ltd.',
        address=('Unit 2208, Airport Freight Forwarding Centre',
                 'Chek Lap Kok', 'Hong Kong'),
        country='Hong Kong',
        tax_label='BR no.',
        tax_id='61925448-000-03-26-A',
        terms='Charges per tariff DHI-2026, air and sea consolidation. Disputes within 14 days.',
        bank_line='',
        style='ledger',
        date_order='day_first',
        decimal_mark='dot',
        number_prefix='DHI',
        accent=(0.72, 0.56, 0.05),
        mode='air',
        surcharges=('Fuel surcharge', 'Security surcharge',
                    'Airport handling', 'Export customs clearance'),
        price_bias=1.18,
        price_spread=0.17,
    ),
    Carrier(
        code='MRK',
        name='Marsk Line Agencies B.V.',
        address=('Pier 9, Terminal Road',
                 'Rotterdam 3089 JS', 'Netherlands'),
        country='Netherlands',
        tax_label='VAT ID',
        tax_id='NL 8201 55 913 B01',
        terms='Ocean freight per service contract MRK-2026-114.',
        bank_line='ING Bank  IBAN NL22 INGB 0007 4411 90',
        style='ledger',
        date_order='iso',
        decimal_mark='dot',
        number_prefix='MRK',
        accent=(0.04, 0.26, 0.45),
        mode='ocean',
        surcharges=('Bunker adjustment factor', 'Terminal handling, origin',
                    'Terminal handling, destination', 'Documentation fee'),
        price_bias=0.96,
        price_spread=0.12,
    ),
    Carrier(
        code='CSM',
        name='COSMO Shipping Lines Co., Ltd.',
        address=('Ocean Tower, 158 Zhongshan Road',
                 'Shanghai 200010', 'China'),
        country='China',
        tax_label='USCC',
        tax_id='91310000MA1FL2QJ7X',
        terms='Subject to COSMO bill of lading terms. Payable on arrival.',
        bank_line='',
        style='grid',
        date_order='iso',
        decimal_mark='dot',
        number_prefix='CSM',
        accent=INK,
        mode='ocean',
        surcharges=('Bunker adjustment factor', 'Congestion surcharge',
                    'Terminal handling, origin', 'Seal and documentation'),
        price_bias=0.89,
        price_spread=0.15,
    ),
    Carrier(
        code='KNG',
        name='Keuhne & Nager Logistics AG',
        address=('Dorfstrasse 50',
                 '8834 Schindellegi', 'Switzerland'),
        country='Switzerland',
        tax_label='VAT no.',
        tax_id='CHE-116.302.419 MWST',
        terms='Rates valid 30 days. Destination charges billed separately.',
        bank_line='UBS Switzerland  IBAN CH93 0076 2011 6238 5295 7',
        style='banded',
        date_order='day_first',
        decimal_mark='comma',
        number_prefix='KNG',
        accent=(0.11, 0.35, 0.18),
        mode='road',
        surcharges=('Inland haulage', 'Port storage', 'Customs brokerage',
                    'Cargo insurance'),
        price_bias=1.08,
        price_spread=0.19,
    ),
)

ALL_ISSUERS = FACTORIES + CARRIERS

#: Who bills Moty inside Brazil, in reais: the truck from the port, and the
#: customs broker, who sends both the duty statement and its own invoice.
#: They join only in the profiles that model the Brazilian import cost, so
#: the quiet run and its ten issuers stay as they are.
TRUCKER = Carrier(
    code='TLV',
    name='Transportes Louveira Ltda.',
    address=('Av. Portuaria, 1450, Macuco', 'Santos, SP 11015-000',
             'Brazil'),
    country='Brazil',
    tax_label='CNPJ',
    tax_id='27.315.640/0001-08',
    terms='CT-e issued on delivery. Payment in 21 days.',
    bank_line='Banco Itau  Ag 0761  Acct 45120-3',
    style='zebra',
    date_order='day_first',
    decimal_mark='comma',
    number_prefix='TLV',
    accent=(0.55, 0.20, 0.10),
    mode='road',
    surcharges=('Pedagio', 'GRIS, cargo insurance', 'Taxa de descarga'),
    price_bias=1.0,
    price_spread=0.10,
    currency='BRL',
)

BROKER = Issuer(
    code='SCA',
    name='Santos Comissaria Aduaneira Ltda.',
    address=('Rua do Comercio, 88, Centro', 'Santos, SP 11010-140',
             'Brazil'),
    country='Brazil',
    tax_label='CNPJ',
    tax_id='09.884.127/0001-33',
    terms='Fees per contract SCA-2026-07.',
    bank_line='Banco Bradesco  Ag 2130  Acct 88412-0',
    style='minimal',
    date_order='day_first',
    decimal_mark='comma',
    number_prefix='SCA',
    accent=(0.20, 0.30, 0.55),
    kind='broker',
    currency='BRL',
)

BRAZIL = (TRUCKER, BROKER)

#: The bonded terminal in Santos, which bills storage in reais.
TERMINAL = Issuer(
    code='TVA',
    name='Terminal Valongo Alfandegado Ltda.',
    address=('Av. Mario Covas Jr., 400, Valongo', 'Santos, SP 11010-150',
             'Brazil'),
    country='Brazil',
    tax_label='CNPJ',
    tax_id='31.507.664/0001-20',
    terms='Armazenagem por periodo, sobre o valor CIF. Tabela TVA-2026.',
    bank_line='Banco do Brasil  Ag 0035  Acct 61207-4',
    style='grid',
    date_order='day_first',
    decimal_mark='comma',
    number_prefix='TVA',
    accent=(0.10, 0.40, 0.45),
    kind='terminal',
    currency='BRL',
)


#: Issuers that appear during a run: new suppliers, with or without an order.
_JOINED = {}


def register(issuer):
    """Make an issuer that joined mid-run findable by its code."""
    _JOINED[issuer.code] = issuer
    return issuer


def by_code(code):
    for issuer in ALL_ISSUERS + BRAZIL + (TERMINAL,):
        if issuer.code == code:
            return issuer
    if code in _JOINED:
        return _JOINED[code]
    raise KeyError(code)


def domain_for(issuer):
    """The mail domain an issuer bills from."""
    return f'{issuer.code.lower()}-billing.example'


def address_for(issuer):
    return f'accounts@{domain_for(issuer)}'


def other_address(issuer):
    """An address the vendor master does not hold: an agent's or a
    colleague's mailbox the bill was sent from by mistake."""
    return f'billing@{issuer.code.lower()}-agent.example'
