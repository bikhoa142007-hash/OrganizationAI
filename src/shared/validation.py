"""Strict JSON contract decoding and immutable values; no framework dependencies."""
from dataclasses import fields, is_dataclass
from datetime import datetime
from hashlib import sha256
import math
import re
from types import MappingProxyType, UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin, get_type_hints
from collections.abc import Mapping

import rfc8785

Hash = Annotated[str, 'hash']
Timestamp = Annotated[str, 'timestamp']
MinorUnits = Annotated[str, 'minor']
Positive = Annotated[int, 'positive']
Nonnegative = Annotated[int, 'nonnegative']


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def json_value(value):
    if is_dataclass(value):
        return {f.name: json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    return value


def canonical_hash(value):
    try:
        return sha256(rfc8785.dumps(json_value(value))).hexdigest()
    except (ValueError, TypeError) as exc:
        raise ValidationError('Not canonicalizable JSON') from exc


def freeze(value):
    if isinstance(value, Mapping):
        require(all(type(k) is str for k in value), 'JSON keys must be strings')
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(freeze(v) for v in value)
    require(value is None or type(value) in (str, bool, int, float), 'Invalid JSON value')
    if type(value) is float:
        require(math.isfinite(value), 'Nonfinite number')
    return value


def decode(tp, value):
    origin, args = get_origin(tp), get_args(tp)
    if tp is Any:
        return freeze(value)
    if origin is Annotated:
        value = decode(args[0], value)
        for marker in args[1:]:
            if marker == 'hash':
                require(re.fullmatch('[0-9a-f]{64}', value), 'Invalid SHA-256')
            elif marker == 'minor':
                require(re.fullmatch('0|[1-9][0-9]*', value), 'Invalid minor units')
            elif marker == 'timestamp':
                require(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z', value), 'Invalid UTC timestamp')
                try:
                    datetime.fromisoformat(value)
                except ValueError as exc:
                    raise ValidationError('Invalid timestamp') from exc
            elif marker == 'positive':
                require(value >= 1, 'Expected positive integer')
            elif marker == 'nonnegative':
                require(value >= 0, 'Expected nonnegative integer')
        return value
    if origin in (Union, UnionType):
        for option in args:
            try:
                return decode(option, value)
            except ValidationError:
                pass
        raise ValidationError('Value does not match union')
    if origin is Literal:
        require(any(type(value) is type(a) and value == a for a in args), 'Unknown enum')
        return value
    if origin is tuple:
        require(type(value) in (tuple, list), 'Expected array')
        return tuple(decode(args[0], x) for x in value)
    if tp is type(None):
        require(value is None, 'Expected null')
    elif tp is float:
        require(type(value) in (int, float) and math.isfinite(value), 'Expected finite number')
    elif tp in (str, int, bool):
        require(type(value) is tp, 'Incorrect primitive type')
        if tp is str:
            require(bool(value.strip()), 'Blank string')
    elif is_dataclass(tp):
        if isinstance(value, tp):
            return value
        return tp.from_dict(value)
    else:
        raise ValidationError('Unsupported contract type')
    return value


class Contract:
    def __post_init__(self):
        for name, tp in get_type_hints(type(self), include_extras=True).items():
            object.__setattr__(self, name, decode(tp, getattr(self, name)))
        self.validate()

    def validate(self):
        pass

    @classmethod
    def from_dict(cls, value):
        require(isinstance(value, Mapping), 'Expected object')
        require(set(value) == {f.name for f in fields(cls)}, 'Missing or unknown fields')
        return cls(**value)

    def to_dict(self):
        return json_value(self)


def distinct(values):
    require(len(values) == len(set(values)), 'Duplicate identifiers')


def paired(left, right):
    require((left is None) == (right is None), 'Unpaired snapshot reference')
