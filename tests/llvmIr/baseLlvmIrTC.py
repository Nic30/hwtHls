from itertools import takewhile
import os
import re

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, parseIR, Function
from tests.baseSsaTest import BaseSsaTC

RE_HWTHLS_FN_CALL = re.compile('call (i[0-9]+) @hwtHls.((bitRangeGet)|(bitConcat))((\.i?[0-9]+)+)\(.*\)( #(\d+))')


def generateAndAppendHwtHlsFunctionDeclarations(llvmIrStr:str):
    indent = "".join(takewhile(lambda x: str.isspace(x) and x != '\n', llvmIrStr))
    declarations = set()
    for fn in RE_HWTHLS_FN_CALL.findall(llvmIrStr):
        retTy = fn[0]
        fnName = fn[1]
        _argTy = fn[4]
        assert fn[7] == "2", (fn[7], "@hwtHls.(bitRangeGet)|(bitConcat) must have memory attribute #2 otherwise it will not be reduced correctly")
        argTy = _argTy.split(".")
        assert argTy[0] == ""
        argTy = argTy[1:]
        if fnName == "bitRangeGet":
            #  %ret = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %1, i6 0) #2
            assert len(argTy) == 2 + 1 + 1, (fn, argTy)
            assert argTy[-2] == retTy, ("wrong bitRangeGet return type", argTy[-2], "!=", retTy)
            declarations.add(f"{indent:s}declare {retTy:s} @hwtHls.bitRangeGet{_argTy:s}({argTy[0]:s} %0, {argTy[1]:s} %1) #1")
        elif fnName == "bitConcat":
            # %ret = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %1, i1 %2, i1 %3) #2
            args = ", ".join(f"{t:s} %{i}" for i, t in enumerate(argTy))
            declarations.add(f"{indent:s}declare {retTy:s} @hwtHls.bitConcat{_argTy:s}({args:s}) #1")

    atts = (f"{indent:s}attributes #1 = {{ nofree nounwind speculatable willreturn }}\n"
            f"{indent:s}attributes #2 = {{ memory(none) }}")
    return "\n".join([llvmIrStr ] + sorted(declarations) + ([atts] if declarations else []))


class BaseLlvmIrTC(BaseSsaTC):

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        raise NotImplementedError("Override this in your implementation of this abstract class")

    def _test_ll(self, irStr: str, passArgs=(), passKwArgs={}):
        irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
        llvm = LlvmCompilationBundle("test")
        Err = SMDiagnostic()
        M = parseIR(irStr, "test", Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            fns = tuple(M)
            llvm.module = M
            llvm.main = fns[0]
            name = llvm.main.getName().str()

        optF = self._runTestOpt(llvm, *passArgs, **passKwArgs)
        self.assert_same_as_file(repr(optF), os.path.join("data", f'{self.__class__.__name__:s}.{name:s}.ll'))
