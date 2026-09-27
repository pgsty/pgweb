"""Manual URL coordinates shared by the reference readers."""
from decimal import Decimal


def manual_slug(tree):
    """Keep pre-10 major.minor identities; tree zero is the devel manual."""
    value = Decimal(str(tree))
    if value == 0:
        return 'devel'
    whole, _, fraction = format(value, 'f').partition('.')
    return whole if value >= 10 else whole + '.' + (fraction.rstrip('0') or '0')
