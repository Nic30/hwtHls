from types import FunctionType, MethodWrapperType, MethodType
from typing import Tuple, Union, List


class BlockLabel(Tuple[Union[int, "PreprocLoopScope", FunctionType, MethodType, MethodWrapperType, "BlockLabel"], ...]):

    def __new__(cls, *args:Union[int, "PreprocLoopScope", FunctionType, MethodType, MethodWrapperType, "BlockLabel"]):
        return tuple.__new__(cls, args)

    def __repr__(self):
        nameParts = []
        for item in self:
            if isinstance(item, (FunctionType, MethodType, MethodWrapperType,)):
                fnName = getattr(item, "__qualname__", item.__name__)
                nameParts.append(fnName)
            else:
                nameParts.append(repr(item))
        res = f'({", ".join(nameParts)})'
        return res


def generateBlockLabel(preprocLoopScope: List["PreprocLoopScope"], blockOffset:int):
    return BlockLabel(*preprocLoopScope, blockOffset)
