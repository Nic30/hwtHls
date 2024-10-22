from enum import Enum


class CHANNEL_ALLOCATION_TYPE(Enum):
    """
    :cvar IMMEDIATE: The signal will be used as is without any buffer. This also means that the value of data is not stable and must be immediately used.
        An extra care must be taken to prove that this kind of buffer does not create a combinational loop.
    :cvar REG: Allocate as a DFF register. Used if it is proven that the size of buffer will be max 1 to spare HW resources and to simplify synchronization logic.
    :cvar BUFFER: Object allocates a buffer of length specified by time difference between read/write.
    """
    IMMEDIATE, REG, BUFFER = range(3)

