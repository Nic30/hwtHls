from bisect import bisect_left
from dis import Instruction

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.statements.statement import HwtSyntaxError
from hwtHls.errors import HlsSyntaxError
from hwtHls.frontend.frame import PyBytecodeFrame


def _getInstAndLineByOffset(instructions: list[Instruction], offset: int):
    thisInstrIndex = bisect_left(instructions, offset, key=lambda i: i.offset)
    assert thisInstrIndex >= 0, offset
    instr = instructions[thisInstrIndex]
    if instr.starts_line is not None:
        instrLine = instr.starts_line
    else:
        instrLine = -1
        for i in reversed(instructions[:thisInstrIndex]):
            if i.starts_line is not None:
                instrLine = i.starts_line
                break
    return instrLine, instr


def createInstructionException(e: Exception, callStack: list[PyBytecodeFrame], frame: PyBytecodeFrame, instr: Instruction):
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

    # add lines with File ... and call site for every calll in call statck
    if callStack[-1] is not frame:
        callStack = callStack + [frame, ]
    msgBuff = []
    parentFrame = None
    for last, f in iter_with_last(callStack):
        f: PyBytecodeFrame
        fn = f.fn
        try:
            if parentFrame is not None:
                # :note: bisect_left is required because instruction offset address space may have holes for python caches
                pFn = parentFrame.fn
                instrLine, callOfThisFrameInstr = _getInstAndLineByOffset(parentFrame.instructions, f.callSiteAddress)
                msgBuff.append(f"File \"{pFn.__globals__['__file__']}\", line {instrLine}, in {pFn.__name__}\n    {callOfThisFrameInstr}\n")

            if last:
                if instr.starts_line is not None:
                    instrLine = instr.starts_line
                else:
                    instrLine = -1
                    thisInstrIndex = bisect_left(frame.instructions, instr.offset, key=lambda i: i.offset)
                    for i in reversed(frame.instructions[:thisInstrIndex]):
                        if i.starts_line is not None:
                            instrLine = i.starts_line
                            break

                msg = f"File \"{fn.__globals__['__file__']}\", line {instrLine}, in {fn.__name__}\n    {instr}\n{e}"
                msgBuff.append(msg)
        except:
            # the exception object itself is broken, reraise it as it is, because there was some issue resolving code
            # locations and the exception can not be wrapped in this case
            raise e from e
        parentFrame = f

    msg = "".join(msgBuff)
    # Dynamically create an exception for:
    # * Compatibility with caller core (e.g. `except OriginalError`)
    errTy = type(e)
    if errTy == HlsSyntaxError or\
       errTy == HlsSyntaxError or\
       errTy == Exception or\
       issubclass(errTy, (HwtSyntaxError, HlsSyntaxError)):
        basesOfException = (errTy,)
    else:
        basesOfException = (errTy, HlsSyntaxError)

    class WrappedException(*basesOfException):
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
