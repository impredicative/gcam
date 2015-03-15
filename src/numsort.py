#!/usr/local/bin/python3.2

## {{{ http://code.activestate.com/recipes/135435/ (r1)
# numsort.py 
# sorting in numeric order 
# for example:
#   ['aaa35', 'aaa6', 'aaa261'] 
# is sorted into:
#   ['aaa6', 'aaa35', 'aaa261']

import functools

@functools.lru_cache(maxsize=None)
def numsorted(alist):
    # inspired by Alex Martelli
    # http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52234
    indices = map(_generate_index, alist)
    decorated = list(zip(indices, alist))
    decorated.sort()
    return [item for index, item in decorated] #@UnusedVariable
    
def _generate_index(astr):
    """
    Splits a string into alpha and numeric elements, which
    is used as an index for sorting"
    """
    #
    # the index is built progressively
    # using the _append function
    #
    index = []
    def _append(fragment, alist=index):
        if fragment.isdigit(): fragment = int(fragment)
        alist.append(fragment)

    # initialize loop
    prev_isdigit = astr[0].isdigit()
    current_fragment = ''
    # group a string into digit and non-digit parts
    for char in astr:
        curr_isdigit = char.isdigit()
        if curr_isdigit == prev_isdigit:
            current_fragment += char
        else:
            _append(current_fragment)
            current_fragment = char
            prev_isdigit = curr_isdigit
    _append(current_fragment)    
    return tuple(index)

    
def _test():
    initial_list = [ 'gad', 'gad-10', 'zeus', 'gad-5', 'gad-0', 'gad-12' ]
    sorted_list = numsorted(initial_list)
    import pprint
    print("Before sorting...")
    pprint.pprint (initial_list)
    print("After sorting...")
    pprint.pprint (sorted_list)
    print("Normal python sorting produces...")
    initial_list.sort()
    pprint.pprint (initial_list)

if __name__ == '__main__':
    _test()
## end of http://code.activestate.com/recipes/135435/ }}}
