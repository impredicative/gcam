"""Provide functions that could potentially have shared use."""

import itertools

def grouper(n, iterable):
    """Return an iterable with items grouped into tuples of length n."""
    # grouper(3, 'ABCDEF') --> ABC DEF
    # Derived from http://docs.python.org/dev/py3k/library/itertools.html#itertools-recipes
    args = [iter(iterable)] * n
    return zip(*args)

def pairwise(iterable):
    """Return an iterable with items grouped pairwise."""
    # pairwise(s) --> (s0,s1), (s1,s2), (s2, s3), ...
    # From http://docs.python.org/dev/py3k/library/itertools.html#itertools-recipes
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)
