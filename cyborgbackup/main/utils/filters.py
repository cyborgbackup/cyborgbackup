import re
from functools import reduce

import django
from pyparsing import (
    infixNotation,
    opAssoc,
    Optional,
    Literal,
    CharsNotIn,
    ParseException,
)

from cyborgbackup.main.utils.common import get_search_fields

__all__ = ['SmartFilter']


def string_to_type(t):
    if t == u'true':
        return True
    elif t == u'false':
        return False

    if re.search(r'^[-+]?[0-9]+$', t):
        return int(t)

    if re.search(r'^[-+]?[0-9]+\.[0-9]+$', t):
        return float(t)

    return t


def get_model(name):
    return django.apps.apps.get_model('main', name)


class SmartFilter(object):
    class BoolOperand(object):
        def __init__(self, t):
            kwargs = dict()
            k, v = self._extract_key_value(t)
            k, v = self._json_path_to_contains(k, v)

            Host = get_model('host')
            search_kwargs = self._expand_search(k, v)
            if search_kwargs:
                kwargs.update(search_kwargs)
                q = reduce(lambda x, y: x | y,
                           [django.db.models.Q(**{u'%s__contains' % _k: _v}) for _k, _v in kwargs.items()])  # noqa
                self.result = Host.objects.filter(q)
            else:
                kwargs[k] = v
                self.result = Host.objects.filter(**kwargs)

        def strip_quotes_traditional_logic(self, v):
            if type(v) is str and v.startswith('"') and v.endswith('"'):
                return v[1:-1]
            return v

        def strip_quotes_json_logic(self, v):
            if type(v) is str and v.startswith('"') and v.endswith('"') and v != u'"null"':
                return v[1:-1]
            return v

        def _json_path_to_contains(self, k, v):
            v = self.strip_quotes_traditional_logic(v)
            return k, v

        def _extract_key_value(self, t):
            t_len = len(t)

            k = None
            v = None

            # key
            # "something"=
            v_offset = 2
            if t_len >= 2 and t[0] == "\"" and t[2] == "\"":
                k = t[1]
                v_offset = 4
            # something=
            else:
                k = t[0]

            # value
            # ="something"
            if t_len > (v_offset + 2) and t[v_offset] == "\"" and t[v_offset + 2] == "\"":
                v = u'"' + str(t[v_offset + 1]) + u'"'
            # empty ""
            elif t_len > (v_offset + 1):
                v = u""
            # no ""
            else:
                v = string_to_type(t[v_offset])

            return k, v

        def _expand_search(self, k, v):
            if 'search' not in k:
                return None

            model, relation = None, None
            if k == 'search':
                model = get_model('host')
            elif k.endswith('__search'):
                relation = k.split('__')[0]
                try:
                    model = get_model(relation)
                except LookupError:
                    raise ParseException('No related field named %s' % relation)

            search_kwargs = {}
            if model is not None:
                search_fields = get_search_fields(model)
                for field in search_fields:
                    if relation is not None:
                        k = '{0}__{1}'.format(relation, field)
                    else:
                        k = field
                    search_kwargs[k] = v
            return search_kwargs

    class BoolBinOp(object):
        def __init__(self, t):
            self.result = None
            i = 2
            while i < len(t[0]):
                if not self.result:
                    self.result = t[0][0].result
                right = t[0][i].result
                self.result = self.execute_logic(self.result, right)
                i += 2

    class BoolAnd(BoolBinOp):
        def execute_logic(self, left, right):
            return left & right

    class BoolOr(BoolBinOp):
        def execute_logic(self, left, right):
            return left | right

    @classmethod
    def query_from_string(cls, filter_string):

        filter_string_raw = filter_string
        filter_string = str(filter_string)

        unicode_spaces = list(set(str(c) for c in filter_string if c.isspace()))
        unicode_spaces_other = unicode_spaces + [u'(', u')', u'=', u'"']
        atom = CharsNotIn(''.join(unicode_spaces_other))
        atom_inside_quotes = CharsNotIn(u'"')
        atom_quoted = Literal('"') + Optional(atom_inside_quotes) + Literal('"')
        EQUAL = Literal('=')

        grammar = ((atom_quoted | atom) + EQUAL + Optional((atom_quoted | atom)))
        grammar.setParseAction(cls.BoolOperand)

        boolExpr = infixNotation(grammar, [
            ("and", 2, opAssoc.LEFT, cls.BoolAnd),
            ("or", 2, opAssoc.LEFT, cls.BoolOr),
        ])

        try:
            res = boolExpr.parseString('(' + filter_string + ')')
        except ParseException:
            raise RuntimeError(u"Invalid query %s" % filter_string_raw)

        if len(res) > 0:
            return res[0].result

        raise RuntimeError("Parsing the filter_string %s went terribly wrong" % filter_string)
