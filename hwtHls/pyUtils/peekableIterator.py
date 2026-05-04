from collections import deque
from typing import  Union, TypeVar, Generator, Self, Iterator


T = TypeVar("T")


class PeekableIterator_HANDLE():
    pass


class PeekableIterator(Iterator[T]):
    """
    Iterator which can be used to peek on current item without consumming it.
    The exceptions raised by iteration are not raised during peek
    based on https://stackoverflow.com/a/10576559
    """

    def __init__(self, iterator: Generator[T], emptyVal=PeekableIterator_HANDLE):
        """
        :param emptyVal: the value returned by peek if there is no more data
        """
        self._peekValue = emptyVal
        self._nextException = None
        self._emptyVal = emptyVal
        self._iterator = iterator
        next(self)  # :note: return inital None, loads first item for peeking

    def __iter__(self) -> Self:
        return self

    def peek(self) -> Union[T, PeekableIterator_HANDLE]:
        return self._peekValue

    def __next__(self) -> T:
        if self._nextException is not None:
            raise self._nextException

        to_return = self._peekValue
        # preload _peekValue for next call of next()
        try:
            self._peekValue = next(self._iterator)
        except Exception as e:
            self._nextException = e
            self._peekValue = self._emptyVal

        return to_return


class PeekableDeque(Iterator[T]):

    def __init__(self, data: deque[T], emptyVal=PeekableIterator_HANDLE):
        """
        :param emptyVal: the value returned by peek if there is no more data
        """
        self._emptyVal = emptyVal
        self._data = data

    def __iter__(self) -> Self:
        return self

    def peek(self) -> Union[T, PeekableIterator_HANDLE]:
        if self._data:
            return self._data[0]
        else:
            return self._emptyVal

    def __next__(self) -> T:
        if not self._data:
            # :note: because popleft() raises IndexError on empty
            raise StopIteration()
        return self._data.popleft()
