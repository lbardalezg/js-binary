"""Parses an object field name/type (mirror of js-binary's ``Field``)."""


class Field:
    def __init__(self, name, type):
        self.optional = False
        if name.endswith("?"):
            self.optional = True
            name = name[:-1]
        self.name = name
        self.array = isinstance(type, (list, tuple))
        if self.array:
            if len(type) != 1:
                raise TypeError("Invalid array type, it must have exactly one element")
            type = type[0]
        from .type import Type

        self.type = Type(type)
