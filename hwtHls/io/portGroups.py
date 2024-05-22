from typing import TypeVar, Union, Type

from hwt.hObjList import HObjList
from hwt.hwIO import HwIO
from hwt.mainBases import RtlSignalBase

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


def getFirstInterfaceInstance(hwIO:Union[HwIO, MultiPortGroup, BankedPortGroup]) -> Union[HwIO, RtlSignalBase]:
    while isinstance(hwIO, (MultiPortGroup, BankedPortGroup)):
        hwIO = hwIO[0]
    return hwIO


def isInstanceOfInterfacePort(hwIO:Union[HwIO, MultiPortGroup, BankedPortGroup], class_: Type[HwIO]) -> bool:
    hwIO = getFirstInterfaceInstance(hwIO)
    return isinstance(hwIO, class_)
