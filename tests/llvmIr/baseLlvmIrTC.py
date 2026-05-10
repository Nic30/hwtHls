from itertools import takewhile, chain
import os
import re
from typing import List

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, SMDiagnostic, parseIR, Function, verifyModule
from tests.baseSsaTest import BaseSsaTC


RE_HWTHLS_FN_CALL = re.compile(r'call (i[0-9]+|void|double) '  # return type
                               r'@hwtHls.('
                                   r'bitRangeGet|bitConcat|'
                                   r'streamWrite|streamWriteStartOfFrame|streamWriteEndOfFrame|streamWrite\.masked|'
                                   r'streamTmpAllocaTmpSetterPlaceholder|'
                                   r'streamRead|streamReadStartOfFrame|streamReadEndOfFrame|'
                                   r'fp\.castToHFloatTmp|'
                                   r'fp\.castHFloatTmpToHFloatTmp|'
                                   r'fp\.castHFloatTmpToHFloatTmpRaw|'
                                   r'fp\.castFromHFloatTmp'
                               r')'  # fn name stem
                               r'((\.(i?[0-9]+|p[0-9]+|isVoid|double))+)'  # '.' separated arg types in function names
                               r'\(.*\)'  # args ignored
                               r'( #(\d+))?'  # attribute id after definition
                               )


def _formatPointerTypeShortAsNormal(ptrType: str) -> str:
    "p2 ->  ptr addrspace(2)"
    assert ptrType.startswith("p"), ptrType
    addrSpace = ptrType[1:]
    if addrSpace == "0":
        return "ptr"
    else:
        return f"ptr addrspace({ptrType[1:]:s})"


def _formatParamsForStreamFnDeclaration(argTy: List[str]):
    return ", ".join(f"{t:s} %{i}" if t.startswith("i") else _formatPointerTypeShortAsNormal(t) for i, t in enumerate(argTy))


def generateAndAppendHwtHlsFunctionDeclarations(llvmIrStr:str):
    indent = "".join(takewhile(lambda x: str.isspace(x) and x != '\n', llvmIrStr))
    declarations = set()
    hasStreamFns = False
    hasFpFns = False
    hfloatTmpConfigArgTypes = ["i1", "i8", "i8", "i1", "i1", "i1", "i1", "i1", "i1", "i8", "i8"]
    for fn in RE_HWTHLS_FN_CALL.findall(llvmIrStr):
        retTy = fn[0]
        fnName = fn[1]
        _argTy = fn[2]
        argTy = _argTy.split(".")
        assert argTy[0] == ""
        argTy = argTy[1:]
        if fnName == "bitRangeGet":
            assert fn[6] == "2", (fn[6], "@hwtHls.bitRangeGet call must have memory attribute #2 otherwise it will not be reduced correctly")
            #  %ret = call i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19 %1, i6 0) #2
            assert len(argTy) == 2 + 1 + 1, (fn, argTy)
            assert argTy[-2] == retTy, ("wrong bitRangeGet return type", argTy[-2], "!=", retTy)
            declarations.add(f"{indent:s}declare {retTy:s} @hwtHls.bitRangeGet{_argTy:s}({argTy[0]:s} %0, {argTy[1]:s} %1) #1")
        elif fnName == "bitConcat":
            assert fn[6] == "2", (fn[6], "@hwtHls.bitConcat call must have memory attribute #2 otherwise it will not be reduced correctly")
            # %ret = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %1, i1 %2, i1 %3) #2
            params = ", ".join(f"{t:s} %{i}" for i, t in enumerate(argTy))
            declarations.add(f"{indent:s}declare {retTy:s} @hwtHls.bitConcat{_argTy:s}({params:s}) #1")
        elif fnName == "streamTmpAllocaTmpSetterPlaceholder":
            # call void @hwtHls.streamTmpAllocaTmpSetterPlaceholder.p0(ptr %txDataOffset)
            # %ret = call i10 @hwtHls.bitConcat.i8.i1.i1(i8 %1, i1 %2, i1 %3) #2
            assert len(argTy) == 1
            params = _formatPointerTypeShortAsNormal(argTy[0])
            declarations.add(f"{indent:s}declare {retTy:s} @hwtHls.streamTmpAllocaTmpSetterPlaceholder{_argTy:s}({params:s})")
        elif fnName in {"streamWrite", "streamWriteStartOfFrame", "streamWriteEndOfFrame", "streamWrite.masked",
                        "streamRead", "streamReadStartOfFrame", "streamReadEndOfFrame"}:
            # call void @hwtHls.streamWriteStartOfFrame.p2(ptr addrspace(2) %tx) #4
            # call void @hwtHls.streamWriteEndOfFrame.p2(ptr addrspace(2) %tx) #4
            # call void @hwtHls.streamWrite.p2.i8.i1(ptr addrspace(2) %tx, i8 %data, i1 %eof) #4
            # call void @hwtHls.streamWrite.masked.p2.i16.i2.i1(ptr addrspace(2) %tx, i16 %data, i2 %mask, i1 %eof) #4
            # %0 = call i10 @hwtHls.streamRead.p2.i64.i10(ptr addrspace(2) %i, i64 8) #4
            assert fn[6] == "4", (fn[6], "@hwtHls.", fnName, " call must have memory attribute #4")
            hasStreamFns = True
            if fnName == "streamRead":
                assert argTy[-1] == retTy, (fn, argTy[-1], retTy)
                argTy = argTy[:-1]
            params = _formatParamsForStreamFnDeclaration(argTy)
            # declare void @hwtHls.streamWrite.p2.isVoid(ptr addrspace(2), i8, i1) #0
            declarations.add(f"{indent:s}declare {retTy:s} @hwtHls.{fnName:s}{_argTy:s}({params:s}) #3")

        elif fnName.startswith("fp."):
            # declare double @hwtHls.fp.castToHFloatTmp.i5(i5, i1, i8, i8, i1, i1, i1, i1, i1, i1, i8, i8) #5
            # declare i5 @hwtHls.fp.castFromHFloatTmp.i5(double, i1, i8, i8, i1, i1, i1, i1, i1, i1, i8, i8) #5
            hasFpFns = True

            if fnName == "fp.castToHFloatTmp":
                assert retTy == "double", (retTy, fn)
            elif fnName == "fp.castFromHFloatTmp":
                assert argTy[0] == retTy, (argTy[0], fn)
                argTy[0] = "double"
            elif fnName == "fp.castHFloatTmpToHFloatTmp":
                assert retTy == "double", (retTy, fn)
                assert argTy[0] == "double", (argTy[0], fn)
            elif fnName == "fp.castHFloatTmpToHFloatTmpRaw":
                assert len(argTy) == 2, argTy
                assert retTy == argTy[1], (retTy, fn)
                assert argTy[0] != "double", (argTy[0], fn)
                assert argTy[1] != "double", (argTy[1], fn)
                argTy = [argTy[0], *hfloatTmpConfigArgTypes]

            params = ", ".join(f"{t:s} %{i}" for i, t in enumerate(chain(argTy, hfloatTmpConfigArgTypes)))
            declarations.add(f"{indent:s}declare {retTy:s} @hwtHls.{fnName:s}{_argTy:s}({params:s}) #5")

    buff = [llvmIrStr]
    buff.extend(sorted(declarations))
    if declarations:
        atts = (
            f"{indent:s}attributes #1 = {{ nofree nounwind speculatable willreturn }}\n"  # for function itself
            f"{indent:s}attributes #2 = {{ memory(none) }}"
        )
        buff.append(atts)
    if  hasStreamFns:
        attrs = (
            f"{indent:s}attributes #3 = {{ nofree nounwind willreturn }}\n"
            f"{indent:s}attributes #4 = {{ memory(argmem: readwrite) }}"
        )
        buff.append(attrs)
    if hasFpFns:
        buff.append(
            f"{indent:s}attributes #5 = {{ nofree nounwind willreturn }}"
        )
    return "\n".join(buff)


class BaseLlvmIrTC(BaseSsaTC):

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        raise NotImplementedError("Override this in your implementation of this abstract class")

    def _test_ll(self, irStr: str, llvmCliArgs=[], passArgs=(), passKwArgs={}, use_generateAndAppendHwtHlsFunctionDeclarations=True):
        if use_generateAndAppendHwtHlsFunctionDeclarations:
            irStr = generateAndAppendHwtHlsFunctionDeclarations(irStr)
        llvm = LlvmCompilationBundle("test", llvmCliArgs)
        Err = SMDiagnostic()
        M = parseIR(irStr, "test", Err, llvm.ctx)
        if M is None:
            raise AssertionError(Err.str("test", True, True))
        else:
            llvm.module = M
            llvm._tryToFindMain()
            name = llvm.main.getName().str()
        if verifyModule(M):
            raise AssertionError()

        optF = self._runTestOpt(llvm, *passArgs, **passKwArgs)
        assert optF is not None
        if verifyModule(M):
            raise AssertionError()
        self.assert_same_as_file(repr(optF), os.path.join("data", f'{self.__class__.__name__:s}.{name:s}.ll'))
