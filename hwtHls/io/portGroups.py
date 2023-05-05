from typing import Tuple, TypeVar

from hwt.synthesizer.interface import Interface

T0 = TypeVar('T0')


class MultiPortGroup(Tuple[T0, 'BankedPortGroup[T0]']):
    """
    A tuple of interfaces which can be accessed concurrently and are accessing same data source/destination.
    """

    def __new__(cls, *args):
        return super(MultiPortGroup, cls).__new__(cls, args)


class BankedPortGroup(Tuple[Interface]):
    """
    A tuple of interfaces which are consecutive ports to the same continuous memory.
    Where each interface can access only corresponding non overlapping part of the memory.
    """

    def __new__(cls, *args):
        return super(BankedPortGroup, cls).__new__(cls, args)
