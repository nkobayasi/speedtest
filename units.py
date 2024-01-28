#!/usr/bin/python
# -*- coding: utf-8 -*-

import re
import math

Ki = 1024**1
Mi = 1024**2
Gi = 1024**3
Ti = 1024**4
Pi = 1024**5

units = (dict(prefix='k', divider=1024**1, singular='K', plural='K'),
         dict(prefix='m', divider=1024**2, singular='M', plural='M'),
         dict(prefix='g', divider=1024**3, singular='G', plural='G'),
         dict(prefix='t', divider=1024**4, singular='T', plural='T'),
         dict(prefix='p', divider=1024**5, singular='P', plural='P'), )

class InvalidUnit(Exception):
    """
    Raised by :py:func:`parse_size()` when a string cannot be parsed into a
    file size:

    >>> from humanfriendly import parse_size
    >>> parse_si_unit('5 Z')
    Traceback (most recent call last):
      File "humanfriendly.py", line 98, in parse_size
        raise InvalidSize, msg % components[1]
    humanfriendly.InvalidUnit: Invalid value unit: 'z'
    """

def round_number(count, keep_width=False):
    """
    Helper for :py:func:`format_size()` and :py:func:`format_timespan()` to
    round a floating point number to two decimal places in a human friendly
    format. If no decimal places are required to represent the number, they
    will be omitted.

    :param count: The number to format.
    :param keep_width: ``True`` if trailing zeros should not be stripped,
                       ``False`` if they can be stripped.
    :returns: The formatted number as a string.

    An example:

    >>> from humanfriendly import round_number
    >>> round_number(1)
    '1'
    >>> round_number(math.pi)
    '3.14'
    >>> round_number(5.001)
    '5'
    """
    text = '%.2f' % float(count)
    if not keep_width:
        text = re.sub('0+$', '', text)
        text = re.sub('\.$', '', text)
    return text

def pluralize(count, singular, plural, whitespace=' '):
    return '%s%s%s' % (count, whitespace, singular if math.floor(float(count)) <= 1 else plural)

def parse_si_unit(value):
    tokens = re.split(r'([0-9.]+)', value.lower())
    components = [s.strip() for s in tokens if s and not s.isspace()]
    if len(components) == 1 and components[0].isdigit():
        # If the string contains only an integer number, it is assumed to be
        # the number of bytes.
        return int(components[0])
    # Otherwise we expect to find two tokens: A number and a unit.
    if len(components) != 2:
        raise InvalidUnit("Expected to get two tokens, got %s!" % components)
    # Try to match the first letter of the unit.
    for unit in reversed(units):
        if components[1].startswith(unit['prefix']):
            return int(float(components[0]) * unit['divider'])
    # Failed to match a unit: Explain what went wrong.
    raise InvalidUnit("Invalid value unit: %r" % components[1])

def format_si_unit(value, keep_width=False):
    for unit in reversed(units):
        if value >= unit['divider']:
            number = round_number(float(value) / unit['divider'], keep_width=keep_width)
            return pluralize(number, unit['singular'], unit['plural'], whitespace='')
    return pluralize(value, '', '', whitespace='')

class IECUnit(object):
    def __init__(self, value):
        if isinstance(value, str):
            self.value = parse_si_unit(value)
        elif isinstance(value, (int, float)):
            self.value = value
        else:
            raise TypeError()

    def __str__(self):
        return format_si_unit(self.value)

    def __cmp__(self, other):
        if isinstance(other, IECUnit):
            return self.value - other.value
        else:
            return self.value - other

    def __eq__(self, other):
        return self.__cmp__(other) == 0

    def __lt__(self, other):
        return self.__cmp__(other) < 0

    def __le__(self, other):
        return self < other or self == other

    def __gt__(self, other):
        return self.__cmp__(other) > 0

    def __ge__(self, other):
        return self > other or self == other

    def __add__(self, other):
        if not isinstance(other, IECUnit):
            other = IECUnit(other)
        return IECUnit(self.value + other.value)

    def __sub__(self, other):
        if not isinstance(other, IECUnit):
            other = IECUnit(other)
        return IECUnit(self.value - other.value)

    def __mul__(self, other):
        if not isinstance(other, (int, float)):
            raise TypeError()
        return IECUnit(self.value * other)

    def __div__(self, other):
        if not isinstance(other, (int, float)):
            raise TypeError()
        return IECUnit(self.value / other)
    
    def __truediv__(self, other):
        return self.__div__(other)

class Bandwidth(IECUnit):
    pass

class VolumeSize(IECUnit):
    pass

def main():
    print(Bandwidth('10M') * 1024)
    print(Bandwidth('100M') < Bandwidth('1G'))
    print(Bandwidth('10M') + Bandwidth('10M'))
    print(Bandwidth('30M') / 2)

if __name__ == '__main__':
    main()
