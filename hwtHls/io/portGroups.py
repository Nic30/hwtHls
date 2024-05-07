from typing import TypeVar, Union, Type

from hwt.synthesizer.hObjList import HObjList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase

T = TypeVar('T')


class MultiPortGroup(HObjList[T]):
    """
    A tuple of interfaces which can be accessed concurrently and are accessing same data source/destination.
    """

    def __hash__(self) -> int:
        return hash(tuple(self))


class BankedPortGroup(HObjList[T]):
    """
    A tuple of interfaces which are consecutive ports to the same continuous memory.
    Where each interface can access only corresponding non overlapping part of the memory.
    """

    def __hash__(self) -> int:
        return hash(tuple(self))


def getFirstInterfaceInstance(intf:Union[Interface, MultiPortGroup, BankedPortGroup]) -> Union[Interface, RtlSignalBase]:
    while isinstance(intf, (MultiPortGroup, BankedPortGroup)):
        intf = intf[0]
    return intf


def isInstanceOfInterfacePort(intf:Union[Interface, MultiPortGroup, BankedPortGroup], class_: Type[Interface]) -> bool:
    intf = getFirstInterfaceInstance(intf)
    return isinstance(intf, class_)
