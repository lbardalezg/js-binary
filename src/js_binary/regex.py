"""A lossless representation of a JavaScript RegExp (source + g/i/m flags)."""

import re

from ._js import normalize_regex_source

_FLAG_ORDER = "gim"


class Regex:
    def __init__(self, source, flags=""):
        if not isinstance(source, str):
            raise TypeError("Expected a string source, got " + repr(source))
        if not isinstance(flags, str):
            raise TypeError("Expected a string flags, got " + repr(flags))
        for flag in flags:
            if flag not in _FLAG_ORDER:
                raise ValueError("Unknown regex flag: " + flag)
        self.source = normalize_regex_source(source)
        self.flags = "".join(flag for flag in _FLAG_ORDER if flag in flags)

    @property
    def global_(self):
        return "g" in self.flags

    @property
    def ignore_case(self):
        return "i" in self.flags

    @property
    def multiline(self):
        return "m" in self.flags

    ignoreCase = ignore_case

    def to_pattern(self):
        flags = 0
        if self.ignore_case:
            flags |= re.IGNORECASE
        if self.multiline:
            flags |= re.MULTILINE
        return re.compile(self.source, flags)

    def __eq__(self, other):
        if isinstance(other, Regex):
            return self.source == other.source and self.flags == other.flags
        return NotImplemented

    def __hash__(self):
        return hash((self.source, self.flags))

    def __repr__(self):
        return "Regex(%r, %r)" % (self.source, self.flags)

    def __str__(self):
        return "/%s/%s" % (self.source, self.flags)
