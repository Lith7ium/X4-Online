"""Parse complete cooperative client-load log snapshots without OS access.

Matching text is not proof of its origin, the bytes X4 loaded, or admission.
The caller owns process and log provenance, freshness and file continuity.
"""
from .load_messages import Offer
from .trusted_load_messages import encode_bound_offer

MAX_LOG = 256 << 20
MAX_LINE = 65536
LOAD_TAG = b'[X4LAN] AUTH_DOWNLOAD_LOAD '
MARKER_TAG = b'AUTH_MARKER '
TICKET_FIELDS = ('world_epoch', 'connection_handle', 'baseline_id', 'load_generation',
                 'checkpoint_id', 'sha256', 'attempt_id', 'slot')


def validate_client_receipts(data, ticket, marker):
    """Require exactly request, inspected marker and observed pause, in order.

    ``ticket`` and ``marker`` are caller-supplied expected values, not verified
    credentials. Other log lines may be present. The result authorizes nothing.
    """
    if type(data) is not bytes or len(data) > MAX_LOG or (data and not data.endswith(b'\n')):
        raise ValueError('client log incomplete or oversized')
    fields = '|'.join(str(ticket[key]) for key in TICKET_FIELDS)
    expected = [
        ('load', ('load_requested|' + fields).encode('ascii')),
        ('marker', b'load INSPECTED ' + marker.encode('ascii')),
        ('load', ('pause_observed|' + fields).encode('ascii')),
    ]
    stage = 0
    for line in data.splitlines():
        if len(line) > MAX_LINE:
            raise ValueError('client log line too long')
        rows = []
        if LOAD_TAG in line:
            rows.append(('load', line.split(LOAD_TAG, 1)[1].strip()))
        if MARKER_TAG in line:
            rows.append(('marker', line.split(MARKER_TAG, 1)[1].strip()))
        for row in rows:
            if stage >= len(expected) or row != expected[stage]:
                raise ValueError('load and marker observations differ or are out of order')
            stage += 1
    if stage != len(expected):
        raise ValueError('load and marker observations differ or are out of order')


def validate_bound_offer_receipts(data, bound, *, slot):
    """Check logged fields against one marker-bound offer and local save slot.

    Offer name and size are not present in these log messages. The caller must
    independently establish those, and must correlate the snapshot to its X4.
    """
    encode_bound_offer(bound)
    # Revalidate fields even if a frozen dataclass was modified by its owner.
    offer = Offer(**{name: getattr(bound.offer, name) for name in Offer.__dataclass_fields__})
    if (type(slot) is not str or len(slot) != 8 or not slot.startswith('save_') or
            not slot[5:].isascii() or not slot[5:].isdigit()):
        raise ValueError('invalid local save slot')
    ticket = {name: getattr(offer, name) for name in TICKET_FIELDS if name != 'slot'}
    ticket['slot'] = slot
    return validate_client_receipts(data, ticket, bound.marker)
