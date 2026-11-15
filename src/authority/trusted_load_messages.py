"""Experimental bounded encoding for cooperative marker-load messages.

This module supplies no transport, peer binding, authentication or freshness.
The receiving connection owner must validate each claim against current state.
"""
import json
import re

from .experimental_client_load import HonestClientLoadClaim
from .load_messages import (MAX_MESSAGE, Offer, Receipt, _pairs, _reject_constant,
                            decode_offer, decode_receipt, encode_offer, encode_receipt)
from .trusted_marker_load_session import MarkerBoundOffer

_MARKER = re.compile(r'[0-9a-f]{32}\Z')


def _marker(value):
    if type(value) is not str or not _MARKER.fullmatch(value):
        raise ValueError('invalid checkpoint marker')
    return value


def _encode(kind, marker, payload, **extra):
    obj = {'version': 1, 'kind': kind, 'marker': _marker(marker),
           'payload': json.loads(payload), **extra}
    raw = json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    if len(raw) > MAX_MESSAGE: raise ValueError('message too large')
    return raw


def encode_bound_offer(bound):
    if type(bound) is not MarkerBoundOffer or type(bound.offer) is not Offer:
        raise ValueError('marker-bound offer required')
    return _encode('marked_offer', bound.marker, encode_offer(bound.offer))


def encode_load_claim(claim):
    if (type(claim) is not HonestClientLoadClaim or type(claim.receipt) is not Receipt
            or claim.load_event_observed is not True or claim.paused_observed is not True):
        raise ValueError('complete cooperative load claim required')
    return _encode('marked_claim', claim.marker, encode_receipt(claim.receipt),
                   load_event_observed=True, paused_observed=True)


def _decode(raw, kind, extra):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_MESSAGE:
        raise ValueError('invalid message size or type')
    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('invalid JSON message') from exc
    if (type(obj) is not dict or set(obj) != {'version', 'kind', 'marker', 'payload'} | set(extra)
            or type(obj['version']) is not int or obj['version'] != 1 or obj['kind'] != kind
            or type(obj['payload']) is not dict):
        raise ValueError('invalid message fields or version')
    _marker(obj['marker'])
    for key in extra:
        if obj[key] is not True: raise ValueError('missing cooperative observation')
    payload = json.dumps(obj['payload'], separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    return obj['marker'], payload


def decode_bound_offer(raw):
    marker, payload = _decode(raw, 'marked_offer', ())
    return MarkerBoundOffer(decode_offer(payload), marker)


def decode_load_claim(raw):
    marker, payload = _decode(raw, 'marked_claim', ('load_event_observed', 'paused_observed'))
    return HonestClientLoadClaim(decode_receipt(payload), marker, True, True)
