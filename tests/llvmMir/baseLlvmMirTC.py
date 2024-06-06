from io import StringIO
import os
from pathlib import Path
import re
from typing import List, Set, Tuple, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, parseMIR, Function
from tests.baseSsaTest import BaseSsaTC


class BaseLlvmMirTC(BaseSsaTC):

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        raise NotImplementedError("Override this in your implementation of this abstract class")

    def _test_mir_file(self):
        nameOfMain = self.getTestName()
        inputFileName = Path(self.__FILE__).expanduser().resolve().parent / "dataIn" / (nameOfMain + ".in.mir.ll")
        with open(inputFileName) as f:
            self._test_mir(f.read(), inputFileName, generateDummyYaml=False)

    def _test_mir(self, mirStr: str, inputFileNameForDebug: Optional[str]=None, generateDummyYaml=True):
        nameOfMain = self.getTestName()
        ctx = LlvmCompilationBundle(nameOfMain)
        if generateDummyYaml:
            buff = StringIO()
            generateFullMirYamlFromMirFunctionStr(mirStr, buff)
            mirStr = buff.getvalue()

        parseMIR(mirStr, nameOfMain, ctx)
        assert ctx.module is not None

        f = ctx.module.getFunction(ctx.strCtx.addStringRef(nameOfMain))
        if inputFileNameForDebug is not None:
            assert f is not None, ("specified file does not contain function of expected name", inputFileNameForDebug, nameOfMain)
        else:
            assert f is not None, ("Specified string does not contain function of expected name", nameOfMain)
        ctx.main = f
        self._runTestOpt(ctx)
        MMI = ctx.getMachineModuleInfo()
        MF = MMI.getMachineFunction(f)
        assert MF is not None
        outFileName = os.path.join("data", self.__class__.__name__ + "." + nameOfMain + ".out.mir.ll")
        self.assert_same_as_file(str(MF), outFileName)


def extractMetaFromMirStr(mirStr: str):
    RE_BLOCK = re.compile("^\s*(bb\.\d+\.([^:]+)):")
    RE_REG = re.compile("%(\d+)(:?\S+)")
    # group4 = io name
    # group6 = addrspace
    RE_IO = re.compile("(load|store) (\(\S+\) )?(from|into) %(\S+)(, align \d+)?, addrspace (\d+)")

    blockNames: List[str] = []
    registers: Set[int] = set()
    mirLines = mirStr.split("\n")
    loadStoreArgs: Set[Tuple[int, str]] = set()
    for line in mirLines:
        blockMatch = RE_BLOCK.match(line)
        if blockMatch:
            blockNames.append(blockMatch.group(2))
            continue
        for regMatch in RE_REG.finditer(line):
            regId = int(regMatch.group(1))
            registers.add(regId)

        for ioMatch in RE_IO.finditer(line):
            _io = (int(ioMatch.group(6)), ioMatch.group(4))
            loadStoreArgs.add(_io)

    return blockNames, sorted(registers), mirLines, sorted(loadStoreArgs)


def generateFullMirYamlFromMirFunctionStr(mirStr: str, out: StringIO):
    blocks, regs, mirLines, loadStoreArgs = extractMetaFromMirStr(mirStr)
    mainName = blocks[0]
    out.write(f"""\
--- |
  source_filename = "{mainName:s}"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @{mainName:s}(""")
    for isLast, (addrspace, argName) in iter_with_last(loadStoreArgs):
        assert argName.startswith("ir."), argName
        argName = argName[3:]
        out.write(f"ptr addrspace({addrspace:d}) %{argName:s}")
        if not isLast:
            out.write(", ")

    out.write(""") {
""")
    for blockName in blocks:
        out.write(f"""     
  {blockName:s}:
    ret void
""")
    out.write("""
  }
 

...
""")
    out.write(f"""\
---
name:            {mainName:s}
alignment:       1
exposesReturnsTwice: false
legalized:       true
regBankSelected: true
selected:        true
failedISel:      false
tracksRegLiveness: true
hasWinCFI:       false
callsEHReturn:   false
callsUnwindInit: false
hasEHCatchret:   false
hasEHScopes:     false
hasEHFunclets:   false
isOutlined:      false
debugInstrRef:   false
failsVerification: false
tracksDebugUserValues: false
registers:
""")
    for reg in regs:
        out.write(f"""\
  - {{ id: {reg:d}, class: anyregcls, preferred-register: '' }}
""")
    out.write("""
liveins:         []
frameInfo:
  isFrameAddressTaken: false
  isReturnAddressTaken: false
  hasStackMap:     false
  hasPatchPoint:   false
  stackSize:       0
  offsetAdjustment: 0
  maxAlignment:    1
  adjustsStack:    false
  hasCalls:        false
  stackProtector:  ''
  functionContext: ''
  maxCallFrameSize: 4294967295
  cvBytesOfCalleeSavedRegisters: 0
  hasOpaqueSPAdjustment: false
  hasVAStart:      false
  hasMustTailInVarArgFunc: false
  hasTailCall:     false
  localFrameSize:  0
  savePoint:       ''
  restorePoint:    ''
fixedStack:      []
stack:           []
entry_values:    []
callSites:       []
debugValueSubstitutions: []
constants:       []
machineFunctionInfo: {}
body:             |
""")
    for mirLine in mirLines:
        out.write("  ")
        out.write(mirLine)
        out.write("\n")

    out.write("""\
...
""")
