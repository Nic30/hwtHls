from typing import List, overload, Union, TypeVar, Iterable, Callable, \
    SupportsIndex
from _collections import deque

_T = TypeVar("_T")


class ObservableListRm():
    pass


class ObservableList(List):

    def __init__(self, *__iterable:Iterable[_T]) -> None:
        list.__init__(self, *__iterable)
        self._beforeSet = None
        self._beforeSetArg = None
        
    def _setObserver(self, beforeSet:Callable[[object, Union[slice, int], Union[object, ObservableListRm]], None], extraArg):
        self._beforeSet = beforeSet
        self._beforeSetArg = extraArg
        
    def __setitem__(self, __s:Union[slice, int], __o:Iterable[_T]) -> None:
        if self._beforeSet:
            self._beforeSet(self._beforeSetArg, self, __s, __o)
        list.__setitem__(self, __s, __o)
    
    def __delitem__(self, __i:int | slice) -> None:
        if self._beforeSet:
            self._beforeSet(self._beforeSetArg, self, __i, ObservableListRm)
        list.__delitem__(self, __i)

    def __iadd__(self, __x:Iterable[_T]):
        self.extend(__x)
        return self

    def append(self, __object:_T) -> None:
        if self._beforeSet:
            self._beforeSet(self._beforeSetArg, self, len(self), __object)
        list.append(self, __object)

    def extend(self, __iterable:Iterable[_T]) -> None:
        if self._beforeSet:
            if not isinstance(__iterable, (tuple, list, deque, set)):
                __iterable = tuple(__iterable)

            index = len(self)
            for i in __iterable:
                self._beforeSet(self._beforeSetArg, self, index, i)
                index += 1
                
        list.extend(self, __iterable)

    def pop(self, *__index) -> _T:
        assert len(__index) <= 1, __index
        if self._beforeSet:
            if __index:
                i = __index[0]
            else:
                i = len(self) - 1
                assert i > 0
            self._beforeSet(self._beforeSetArg, self, i, ObservableListRm)            
        return list.pop(self, *__index)

    def remove(self, __value:_T) -> None:
        if self._beforeSet:
            self._beforeSet(self._beforeSetArg, self, self.index(), ObservableListRm)   
        list.remove(self, __value)

    def insert(self, __index:SupportsIndex, __object:_T) -> None:
        raise NotImplementedError()

    def clear(self) -> None:
        if self._beforeSet:
            for i, _ in enumerate(self):
                self._beforeSet(self._beforeSetArg, self, i, None)
        
        list.clear(self)
