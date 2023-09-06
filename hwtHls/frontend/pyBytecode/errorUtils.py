from dis import Instruction

from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame


def createInstructionException(e: Exception, frame: PyBytecodeFrame, instr: Instruction):
    """
    based on https://github.com/google/etils/blob/main/etils/epy/reraise_utils.py#L38
    
    Re-raise an exception with an additional message.
    Benefit: Contrary to `raise ... from ...` and
    `raise Exception().with_traceback(tb)`, this function will:
    * Keep the original exception type, attributes,...
    * Avoid multi-nested `During handling of the above exception, another
      exception occurred`. Only the single original stacktrace is displayed.
    This result in cleaner and more compact error messages.
    Usage:
    .. code-block::
        try:
            fn(x)
        except Exception as e:
            raise createInstructionException(e, frame, instr) from e.__cause__
    """
    if instr.starts_line is not None:
        instrLine = instr.starts_line
    else:
        instrLine = -1
        for i in reversed(frame.instructions[:frame.instructions.index(instr)]):
            if i.starts_line is not None:
                instrLine = i.starts_line
                break

    fn = frame.fn
    msg = f"File \"{fn.__globals__['__file__']}\", line {instrLine}, in {fn.__name__}\n    {instr}\n{e}"
    
    # Dynamically create an exception for:
    # * Compatibility with caller core (e.g. `except OriginalError`)
    
    class WrappedException(type(e), HlsSyntaxError):
        """Exception proxy with additional message about code location in user code."""
        
        def __init__(self, msg):
            # We explicitly bypass super() as the `type(e).__init__` constructor
            # might have special kwargs
            Exception.__init__(self, msg)  # pylint: disable=non-parent-init-called
        
        def __getattr__(self, name: str):
            # Capture `e` through closure. We do not pass e through __init__
            # to bypass `Exception.__new__` magic which add `__str__` artifacts.
            return getattr(e, name)
        
        # The wrapped exception might have overwritten `__str__` & cie, so
        # use the base exception ones.
        __repr__ = BaseException.__repr__
        __str__ = BaseException.__str__
    
    WrappedException.__name__ = type(e).__name__
    WrappedException.__qualname__ = type(e).__qualname__
    WrappedException.__module__ = type(e).__module__
    new_exception = WrappedException(msg)
    
    # Propagate the exception:
    # * `with_traceback` will propagate the original stacktrace
    # * `from e.__cause__` will:
    #   * Propagate the original `__cause__` (likely `None`)
    #   * Set `__suppress_context__` to True, so `__context__` isn't displayed
    #     This avoid multiple `During handling of the above exception, another
    #     exception occurred:` messages when nesting `reraise`
    return new_exception.with_traceback(e.__traceback__)
