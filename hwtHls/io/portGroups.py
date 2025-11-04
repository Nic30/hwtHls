from typing import TypeVar, Union, Type, Callable

from hwt.hwIO import HwIO
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.mainBases import RtlSignalBase

T = TypeVar('T')


class MultiPortGroup(HwIOArray[T]):
    """
    A tuple of interfaces which can be accessed concurrently and are accessing same data source/destination.
    """

    # :attention: override of __eq__, __hash__ are required because port groups are generated
    #   dynamically on multiple places so equal tuple may be constructed but it is not necessary the same object
    def __eq__(self, other):
        return self.__class__ is other.__class__ and list.__eq__(self, other)

    def __hash__(self) -> int:
        return hash(tuple(self))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {self._name if self._name is not None else ''} {list.__repr__(self)}>"


class BankedPortGroup(HwIOArray[T]):
    """
    A tuple of interfaces which are consecutive ports to the same continuous memory.
    Where each interface can access only corresponding non overlapping part of the memory.
    """

    def __eq__(self, other):
        return  self.__class__ is other.__class__ and list.__eq__(self, other)

    def __hash__(self) -> int:
        return hash(tuple(self))

    def __repr__(self) -> str:
        return MultiPortGroup.__repr__(self)

# :note: VectorPortGroup (tuple of interfaces are ports of parallel interfaces accessed always with the same patern) = HwIOArray itself


def iterAllPortGroupVariants(hwIO:Union[HwIO, MultiPortGroup, BankedPortGroup]):
    yield hwIO
    if isinstance(hwIO, (MultiPortGroup, BankedPortGroup)):
        for g in hwIO:
            yield from iterAllPortGroupVariants(g)


def getFirstInterfaceInstance(hwIO:Union[HwIO, MultiPortGroup, BankedPortGroup],
                              instanceFilter: Callable[Union[HwIO, RtlSignalBase], bool]=None)\
        ->Union[HwIO, RtlSignalBase, MultiPortGroup, BankedPortGroup]:
    while isinstance(hwIO, (MultiPortGroup, BankedPortGroup)):
        if instanceFilter is not None:
            # try to seach for first object satisfying instanceFilter predicate
            for _hwIO in hwIO:
                _hwIO = getFirstInterfaceInstance(_hwIO, instanceFilter)
                if _hwIO is not None:
                    return _hwIO
            return None
        else:
            # take first instance because there is no predicate
            hwIO = hwIO[0]
    if instanceFilter is not None:
        if instanceFilter(hwIO):
            return hwIO
        else:
            return None
    else:
        return hwIO


def isInstanceOfInterfacePort(hwIO:Union[HwIO, MultiPortGroup, BankedPortGroup], class_: Type[HwIO]) -> bool:
    hwIO = getFirstInterfaceInstance(hwIO)
    return isinstance(hwIO, class_)
