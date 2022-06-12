from typing import Tuple, Union, List


BlockLabel = Tuple[Union[int, "PreprocLoopScope"], ...]


def generateBlockLabel(preprocLoopScope: List["PreprocLoopScope"], blockOffset:int):
    return (*preprocLoopScope, blockOffset)
