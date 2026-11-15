"""Experimental bounded load-offer encoding; no transport or load confirmation.

These values are untrusted data. A matching receipt proves neither origin nor
that X4 loaded anything. Callers must authenticate and fence the real operation.
"""
from dataclasses import asdict, dataclass
import json
import re

MAX_MESSAGE = 4096
MAX_INTEGER = (1 << 53) - 1
MAX_SAVE_SIZE = 512 * 1024 * 1024
_EPOCH = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_ATTEMPT = re.compile(r'[0-9a-f]{32}\Z')
_CHECKPOINT = re.compile(r'checkpoint-[0-9a-f]{32}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_NAME = re.compile(r'j[1-9][0-9]{0,6}\.xml\.gz\Z')


def _text(value, pattern, field):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError('invalid ' + field)


def _integer(value, upper, field):
    if type(value) is not int or not 1 <= value <= upper:
        raise ValueError('invalid ' + field)


@dataclass(frozen=True)
class Receipt:
    world_epoch: str
    connection_handle: int
    baseline_id: int
    load_generation: int
    attempt_id: str
    checkpoint_id: str
    sha256: str
    size: int

    def __post_init__(self):
        _text(self.world_epoch, _EPOCH, 'world epoch')
        for field in ('connection_handle', 'baseline_id', 'load_generation'):
            _integer(getattr(self, field), MAX_INTEGER, field)
        _text(self.attempt_id, _ATTEMPT, 'attempt ID')
        _text(self.checkpoint_id, _CHECKPOINT, 'checkpoint ID')
        _text(self.sha256, _SHA, 'SHA-256')
        _integer(self.size, MAX_SAVE_SIZE, 'size')


@dataclass(frozen=True)
class Offer(Receipt):
    name: str

    def __post_init__(self):
        super().__post_init__()
        _text(self.name, _NAME, 'offer name')


def from_load_offer(offer, attempt_id):
    """Copy an offer under this codec's stricter limits; not all LoadOffers fit."""
    from .save_transfer import SaveOffer
    from .world import LoadOffer

    if type(offer) is not LoadOffer or type(offer.save) is not SaveOffer:
        raise ValueError('coordinator LoadOffer required')
    return Offer(world_epoch=offer.world_epoch, connection_handle=offer.connection_handle,
                 baseline_id=offer.baseline_id, load_generation=offer.load_generation,
                 attempt_id=attempt_id, checkpoint_id=offer.save.checkpoint_id,
                 sha256=offer.save.sha256, size=offer.save.size, name=offer.save.name)


def matches_offer(receipt, offer):
    """Compare provided fields only; no freshness, filename binding or authentication."""
    if type(receipt) is not Receipt or type(offer) is not Offer:
        raise ValueError('receipt and offer required')
    return all(getattr(receipt, field) == getattr(offer, field)
               for field in Receipt.__dataclass_fields__)


def _encode(value, expected, kind):
    if type(value) is not expected:
        raise ValueError('wrong message type')
    message = {'version': 1, 'kind': kind, **asdict(value)}
    encoded = json.dumps(message, ensure_ascii=True, allow_nan=False,
                         sort_keys=True, separators=(',', ':')).encode('ascii')
    if len(encoded) > MAX_MESSAGE:
        raise ValueError('message too large')
    return encoded


def encode_offer(offer):
    return _encode(offer, Offer, 'offer')


def encode_receipt(receipt):
    return _encode(receipt, Receipt, 'receipt')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate message field')
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError('non-finite JSON number')


def _decode(raw, expected, kind):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_MESSAGE:
        raise ValueError('invalid message size or type')
    try:
        message = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                             parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('invalid JSON message') from exc
    fields = set(expected.__dataclass_fields__) | {'version', 'kind'}
    if (type(message) is not dict or set(message) != fields or
            type(message['version']) is not int or message['version'] != 1 or
            message['kind'] != kind):
        raise ValueError('invalid message fields or version')
    return expected(**{key: value for key, value in message.items()
                       if key not in ('version', 'kind')})


def decode_offer(raw):
    return _decode(raw, Offer, 'offer')


def decode_receipt(raw):
    return _decode(raw, Receipt, 'receipt')
