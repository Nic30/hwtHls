import inspect
from pathlib._local import Path
from typing import Optional, Callable, Sequence, Union, Self

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.netlist.analysis.hlsNetlistSimulator import HlsNetlistSimulator
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtSimApi.triggers import StopSimumulation
from hwtSimApi.utils import freq_to_period
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.passTestInjector import PassTestInjector
from tests.passTestIo import PassTestIo, PassTestIoIn, PassTestIoOut, PassTestIoToFlatten


class HlsModelFnProps():
    """
    :param returnsPyValue: if true the model output values are passed to PassTestIo without
        a cast, else to_py() is applied
    :param returnsOutValue: if True the return/yield value of model is appended as
        another output of the function
    :param inputArgsAreStructMembers: if True all args of model are theated as members of a single input of struct type
    
    .. code-block::python
       @hlsModelProps(inputArgsAreStructMembers=True)
       def model(a, b):
           # there is a single input struct {a; b}, but for model the members of input struct are automatically expanded
           # to arguments of this model function
           pass
    
    # :param modelInputsAreUnpackedStruct: if True the input should be HStruct or PassTestIoInStruct
    #     and the model function should have members of he struct as agruments.
    #     So the input data are unpacked before passing to model
    # :param modelOutputsAreUnpackedStruct:  same as modelInputsAreUnpackedStruct just for outputs
    """

    def __init__(self, returnsPyValue: bool=False, returnsOutValue:bool=False, inputArgsAreStructMembers:bool=False):
        self.returnsPyValue = returnsPyValue  
        self.returnsOutValue = returnsOutValue
        self.inputArgsAreStructMembers = inputArgsAreStructMembers
    
    def __call__(self, fn):
        fn._HlsModelFnProps = self
        return fn

    @classmethod
    def getForModelFn(cls, fn) -> Self:
        props = getattr(fn, "_HlsModelFnProps", None)
        if props is None:
            props = cls()
            fn._HlsModelFnProps = props
        
        return props
    
    def resolveEmptyOutDataContainers(self, modelFn: Optional[Callable[[Sequence[HBitsConst], ...], None]],
                                      IN_DATA_CNT: int,
                                      OUT_DATA_REF: tuple[Union[PassTestIo, list[HBitsConst]], ...],
                                      ):
        # infer rtl port names and argument count from model function
        argCnt = modelFn.__code__.co_argcount
        code = modelFn.__code__
        if self.inputArgsAreStructMembers:
            outCnt = 0
            PORT_NAMES = (None,)
        else:
            if inspect.ismethod(modelFn):
                # ommit "self"
                PORT_NAMES = code.co_varnames[1:argCnt]
                argCnt -= 1
            else:
                PORT_NAMES = code.co_varnames[:argCnt]
            
            outCnt = argCnt - IN_DATA_CNT 

        if self.returnsOutValue:
            outCnt += 1
            PORT_NAMES = (*PORT_NAMES, None)

        if OUT_DATA_REF is None:
            outRefData = [[] for _ in range(outCnt)]
        else:
            assert len(OUT_DATA_REF) == outCnt, ("the model function have unexpected number of out args",
                                                 PORT_NAMES, self.returnsOutValue, len(OUT_DATA_REF), outCnt, modelFn)
            outRefData = OUT_DATA_REF
            for o in OUT_DATA_REF:
                if isinstance(o, PassTestIoOut):
                    assert len(o.dataRef) == 0, o
                else:
                    assert len(o) == 0, o
        return PORT_NAMES, outRefData

    def runModelAndCollectRefData(self, modelFn: Optional[Callable[[Sequence[HBitsConst], ...], None]], TEST_IO: tuple[PassTestIo]):
        assert TEST_IO is not None, "The test data was not set"
        modelArgs: list[Union[Sequence[HBitsConst], list[HBitsConst]]] = []
        modelArgsRaw: list[Union[Sequence[HBitsConst], PassTestIoToFlatten, list[HBitsConst]]] = []
        for io in TEST_IO:
            ioArg = io.getForModel()
            modelArgsRaw.append(ioArg)
            PassTestIoToFlatten.appendUnwrapped(ioArg, modelArgs)
            
        if inspect.isgeneratorfunction(modelFn):
            if self.returnsOutValue:
                raise NotImplementedError()
            m = modelFn(*modelArgs)
            try:
                while True:
                    next(m)
            except StopIteration:
                pass
            except StopSimumulation:
                pass

        else:
            if self.returnsOutValue:
                inData = modelArgs[:len(modelArgs) - 1]
                outData = modelArgs[-1]
                # :attention: this expects that all input data are of the same length
                for d in zip(*inData):
                    try:
                        o = modelFn(*d)
                        outData.append(o)
                    except StopIteration:
                        pass
                    except StopSimumulation:
                        pass

            else:
                try:
                    modelFn(*modelArgs)
                except StopIteration:
                    pass
                except StopSimumulation:
                    pass

        # set collected data to TEST_IO output reference data
        for resData, refData in zip(modelArgsRaw, TEST_IO):
            refData: PassTestIo
            if isinstance(refData, PassTestIoOut):
                if not self.returnsPyValue:
                    resData = [d.to_py() for d in resData]
                refData.setDataRef(resData)


def hlsModelProps(returnsPyValue: bool=False, returnsOutValue: bool=False, inputArgsAreStructMembers:bool=False):
    """
    decorator which adds HlsModelFnProps to model function
    
    .. code-block:: python
        @hlsModelProps(returnsPyValue=True)
        def model(dataIn: Sequence[HBitsConst]) -> Generator[int, None, None]:
            for d in dataIn:
                yield 1
    """
    return HlsModelFnProps(returnsPyValue, returnsOutValue, inputArgsAreStructMembers)
    

class PassTestInjectorForDInDOutHwModule(PassTestInjector):
    """
    Executes tests as specified with IN_DATA and check that out values equal OUT_DATA_REF.
    
    :ivar IN_DATA: tuple of list with input values for each input
    :ivar OUT_DATA_REF: tuple of list with output expected values for each output
    :ivar _wallTimeIr: max number of clock cycles for LLVM IR simulation (1 instr = 1 clk)
    :ivar _wallTimeMir: max number of clock cycles for LLVM MIR simulation (1 instr = 1 clk)
    :ivar _wallTimeRtl: max number of clock cycles for RTL simulation
    :ivar _wallTimeRtlDefaultMultiplier: see :meth:`~.getWallTimeRtlClksDefault`
    :ivar _wallTimeRtlDefaultAddAfter: see :meth:`~.getWallTimeRtlClksDefault`
    """

    def __init__(self, topToRunTestsOn:HwModule, tc: SimTestCase):
        super().__init__(topToRunTestsOn, tc)
        self.TEST_IO: Optional[tuple[PassTestIo, ...]] = None
        self._wallTimeIr: Optional[int] = None
        self._wallTimeMir: Optional[int] = None
        self._wallTimeHlsNetlist: Optional[int] = None
        self._wallTimeRtl: Optional[int] = None
        self._wallTimeRtlDefaultMultiplier: float | int = 1
        self._wallTimeRtlDefaultAddAfter: int = 0

    def bindData(self, TEST_IO: tuple[PassTestIo, ...]):
        self.TEST_IO = TEST_IO
        for ptIo in TEST_IO:
            ptIo: PassTestIo
            ptIo.bindPassTestInjector(self)

    def _bindData_normalizeIn(self, name: str, rtlPresetBeforeClk:bool, inD: Union[PassTestIo, list[HBitsConst]], randomizeControl: Optional[bool]):
        if isinstance(inD, PassTestIo):
            ptIo = inD
            if name is None:
                pass
            elif ptIo.name is None:
                ptIo.name = name
            else:
                assert ptIo.name == name, (ptIo.name, name)
            if randomizeControl is not None:
                ptIo.randomizeControl = randomizeControl
        else:
            ptIo = PassTestIoIn(inD, name, rtlPresetBeforeClk=rtlPresetBeforeClk,
                                randomizeControl=bool(randomizeControl))
        return ptIo

    def _bindData_normalizeOut(self, name: str, rtlPresetBeforeClk:bool,
                               itemCntLimit:Optional[int], outDataRef: Union[PassTestIo, list[HBitsConst]],
                               randomizeControl: Optional[bool]):
        if isinstance(outDataRef, PassTestIo):
            ptIo = outDataRef
            if name is None:
                pass
            elif ptIo.name is None:
                ptIo.name = name
            else:
                assert ptIo.name == name, (ptIo.name, name)
            if itemCntLimit is None:
                pass
            elif ptIo.itemCntLimit is None:
                ptIo.itemCntLimit = itemCntLimit
            else:
                assert ptIo.itemCntLimit == itemCntLimit
            if randomizeControl is not None:
                ptIo.randomizeControl = randomizeControl
        else:
            ptIo = PassTestIoOut(outDataRef, itemCntLimit=itemCntLimit, name=name,
                                 rtlPresetBeforeClk=rtlPresetBeforeClk,
                                 randomizeControl=bool(randomizeControl))
        return ptIo

    def bindDataByInOut(self,
                 IN_DATA: tuple[Union[PassTestIo, list[HConst]], ...],
                 OUT_DATA_REF: tuple[Union[PassTestIo, list[HConst]], ...],
                 OUT_ITEM_CNT_LIMITS:Optional[tuple[Optional[int], ...]]=None,
                 IO_CONTROL_RANDOMIZE: Optional[tuple[Optional[Optional[bool]], ...]]=None,
                 PORT_NAMES=("data_in", "data_out"),
                 rtlPresetBeforeClk=True,
                ):
        """
        Utility function to build PassTestIo objects from raw data lists etc. 
        :note: assumes that arguments are in format inputs, outputs
        """
        expectedPortCnt = len(IN_DATA) + len(OUT_DATA_REF)
        if PORT_NAMES is None:
            portNameIt = (None for _ in range(expectedPortCnt))
        else:
            portNameIt = iter(PORT_NAMES)
            assert len(PORT_NAMES) == expectedPortCnt, (len(PORT_NAMES), len(IN_DATA), len(OUT_DATA_REF))

        if IO_CONTROL_RANDOMIZE is None:
            IO_CONTROL_RANDOMIZE_it = (None for _ in range(expectedPortCnt))
        else:
            assert len(IO_CONTROL_RANDOMIZE) == expectedPortCnt, (len(IO_CONTROL_RANDOMIZE), expectedPortCnt)
            IO_CONTROL_RANDOMIZE_it = iter(IO_CONTROL_RANDOMIZE)

        TEST_IO = []
        self.TEST_IO = TEST_IO
        for inD in IN_DATA:
            name = next(portNameIt)
            randomizeControl = next(IO_CONTROL_RANDOMIZE_it)
            ptIo = self._bindData_normalizeIn(name, rtlPresetBeforeClk, inD, randomizeControl)
            ptIo.bindPassTestInjector(self)
            TEST_IO.append(ptIo)

        if OUT_ITEM_CNT_LIMITS is None:
            OUT_ITEM_CNT_LIMITS = (None for _ in range(len(OUT_DATA_REF)))

        for outDataRef, itemCntLimit in zip(OUT_DATA_REF, OUT_ITEM_CNT_LIMITS):
            name = next(portNameIt)
            randomizeControl = next(IO_CONTROL_RANDOMIZE_it)
            ptIo = self._bindData_normalizeOut(name, rtlPresetBeforeClk, itemCntLimit, outDataRef, randomizeControl)
            ptIo.bindPassTestInjector(self)
            TEST_IO.append(ptIo)

    def setTimeLimits(self,
                       wallTimeIr: Optional[int]=NOT_SPECIFIED,
                       wallTimeMir: Optional[int]=NOT_SPECIFIED,
                       wallTimeHlsNetlist: Optional[int]=NOT_SPECIFIED,
                       wallTimeRtl: Optional[int]=NOT_SPECIFIED,
                       wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,
                       wallTimeRtlDefaultAddAfter:Optional[int]=NOT_SPECIFIED
                      ):
        """
        :see: meaning of times in this class doc
        """
        if wallTimeIr is not NOT_SPECIFIED:
            self._wallTimeIr = wallTimeIr
        if wallTimeMir is not NOT_SPECIFIED:
            self._wallTimeMir = wallTimeMir
        if wallTimeHlsNetlist is not NOT_SPECIFIED:
            self._wallTimeHlsNetlist = wallTimeHlsNetlist
        if wallTimeRtl is not NOT_SPECIFIED:
            self._wallTimeRtl = wallTimeRtl
        if wallTimeRtlDefaultMultiplier is not NOT_SPECIFIED:
            self._wallTimeRtlDefaultMultiplier = wallTimeRtlDefaultMultiplier
        if wallTimeRtlDefaultAddAfter is not NOT_SPECIFIED:
            self._wallTimeRtlDefaultAddAfter = wallTimeRtlDefaultAddAfter

    def checkForLlvmIr(self, simArgs: tuple[list[HBitsConst]]):
        for resData, refData in zip(simArgs, self.TEST_IO):
            refData: PassTestIo
            if isinstance(refData, PassTestIoOut):
                refData.checkForLlvmIr(resData)

    def checkForLlvmMir(self, simArgs: tuple[list[HBitsConst]]):
        for resData, refData in zip(simArgs, self.TEST_IO):
            refData: PassTestIo
            if isinstance(refData, PassTestIoOut):
                refData.checkForLlvmMir(resData)

    def checkForHlsNetlist(self, simArgs: tuple[list[HBitsConst]]):
        for resData, refData in zip(simArgs, self.TEST_IO):
            refData: PassTestIo
            if isinstance(refData, PassTestIoOut):
                refData.checkForHlsNetlist(resData)

    def checkForRtl(self):
        """
        function called after RTL similation to test if output is correct
        """
        for refData in self.TEST_IO:
            refData: PassTestIo
            if isinstance(refData, PassTestIoOut):
                refData.checkForRtl()

    @staticmethod
    def backupFileFileIfExits(path: str | Path) -> Path | None:
        src = Path(path)

        if not src.exists():
            return None

        dst = src.with_name(src.stem + ".bkp" + src.suffix)
        src.replace(dst)
        return dst

    @override
    def testLlvmIrOrMir(self, platform: VirtualHlsPlatform, toLlvm: ToLlvmIrTranslator, isMir: bool):
        """
        Execute interpret on optimized IR with product of createDataInDataOut function and then call checkDataOutFn  
        """
        llvm = toLlvm.llvm
        mainPortNames = tuple(a.getName().str() for a in llvm.main.args())
        
        assert self.TEST_IO is not None, ("PORT_NAMES were not set", mainPortNames)
        if self.TEST_IO[-1].name is None:
            # handle return name
            self.TEST_IO[-1].name = mainPortNames[-1]
        
        expectedPortNames = tuple(ptIo.name for ptIo in self.TEST_IO)
        # if len(mainPortNames) == expectedPortNames:
        #    # :note name may be None if it represents return
        #    expectedPortNames = [e if e is not None else cur for e, cur in zip(expectedPortNames, mainPortNames)]
        assert mainPortNames == expectedPortNames, ("real PORT_NAMES are not expected PORT_NAMES", mainPortNames, expectedPortNames)

        if isMir:
            args = [io.getForLlvmMir() for io in self.TEST_IO]
        else:
            args = [io.getForLlvmIr() for io in self.TEST_IO]

        logFileNameStem = self._logFileNameStem
        if llvm.main is None:
            raise NotImplementedError("Mutithread sim")

        if isMir:
            interpret = LlvmMirInterpret(llvm, toLlvm.placeholderObjectSlots, platform._componentGenerators, args)
            waveLogFileName = str(logFileNameStem) + ".llvmMirWave.vcd"
            wallTime = self._wallTimeMir
        else:
            interpret = LlvmIrInterpret(llvm, toLlvm.placeholderObjectSlots, platform._componentGenerators, platform._getHFloatType, args)
            waveLogFileName = str(logFileNameStem) + ".llvmIrWave.vcd"
            wallTime = self._wallTimeIr

        self.backupFileFileIfExits(waveLogFileName)
        try:
            # gdbLlvmIrHandler = GdbCmdHandlerLllvmIr(interpret, args)
            # gdbServer = GDBServerStub(gdbLlvmIrHandler)
            # gdbServer.start()
            if wallTime is not None:
                wallTime *= interpret.timeStep

            if logFileNameStem is not None:
                with open(waveLogFileName, "w") as vcdFile:
                    waveLog = VcdWriter(vcdFile)
                    interpret.installWaveLog(waveLog)
                    interpret.run(wallTime=wallTime)
            else:
                interpret.run(wallTime=wallTime)
        except SimIoUnderflowErr:
            pass  # all inputs consumed
        except StopSimumulation:
            pass

        if isMir:
            self.checkForLlvmMir(args)
        else:
            self.checkForLlvmIr(args)

    @override
    def testHlsNetlist(self, platform: VirtualHlsPlatform, netlist: HlsNetlistCtx):
        waveLogFileName = f"{str(self._logFileNameStem)}.hlsNetlistWave.vcd"
        self.backupFileFileIfExits(waveLogFileName)
        args = [io.getForHlsNetlist() for io in self.TEST_IO]
        wallTime = self._wallTimeHlsNetlist

        try:
            with open(waveLogFileName, "w") as vcdFile:
                waveLog = VcdWriter(vcdFile)
                interpret = HlsNetlistSimulator(netlist, args)
                interpret.installWaveLog(waveLog)
                if wallTime is not None:
                    wallTime *= interpret.timeStep
                interpret.run(wallTime=wallTime)
        except SimIoUnderflowErr:
            pass  # all inputs consumed
        except StopSimumulation:
            pass

        self.checkForHlsNetlist(args)

    def getWallTimeRtlClksDefault(self) -> int:
        return int(max(ptIo.getRtlDataLen() for ptIo in self.TEST_IO) * self._wallTimeRtlDefaultMultiplier + 1) + self._wallTimeRtlDefaultAddAfter

    def testRtl(self):
        dut = self._topToRunTestsOn
        tc = self.tc

        for ptIo in self.TEST_IO:
            ptIo: PassTestIo
            if isinstance(ptIo, PassTestIoIn):
                ptIo.getForRtl()

        wallTimeRtlClks = self._wallTimeRtl
        if wallTimeRtlClks is None:
            wallTimeRtlClks = self.getWallTimeRtlClksDefault()

        t = int(wallTimeRtlClks * freq_to_period(dut.CLK_FREQ))
        tc.runSim(t)
        self.checkForRtl()
    
    def initTestOutDataRefUsingModel(self, IN_DATA: tuple[Union[PassTestIoIn, Sequence[HConst]], ...],
                    OUT_DATA_REF: Optional[tuple[Union[PassTestIo, list[HBitsConst]], ...]]=None,
                    OUT_ITEM_CNT_LIMITS: Optional[tuple[Optional[int], ...]]=None,
                    IO_CONTROL_RANDOMIZE: Optional[tuple[Optional[Optional[bool]], ...]]=None,
                    model: Optional[Callable[[Sequence[HConst], ...], None]]=None,):
        dut = self._topToRunTestsOn
        if model is None:
            model = dut.model
        
        modelProps: HlsModelFnProps = HlsModelFnProps.getForModelFn(model)
        inCnt = 1 if modelProps.inputArgsAreStructMembers else len(IN_DATA)
        PORT_NAMES, outRefData = modelProps.resolveEmptyOutDataContainers(model, inCnt, OUT_DATA_REF)
        self.bindDataByInOut(IN_DATA, outRefData, OUT_ITEM_CNT_LIMITS=OUT_ITEM_CNT_LIMITS,
                             IO_CONTROL_RANDOMIZE=IO_CONTROL_RANDOMIZE, PORT_NAMES=PORT_NAMES)
        modelProps.runModelAndCollectRefData(model, self.TEST_IO)

    def test_allInOne(self,
                      platform:Optional[VirtualHlsPlatform]=None,
                      platformKwArgs=dict(
                          # debugFilter={  # *HlsDebugBundle.ALL_RELIABLE,
                          # # HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                          # # HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                          # },
                          # llvmCliArgs=[
                          #    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          #    # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                          #    # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                          # ],
                      ),
                      ):
        assert self.TEST_IO is not None
        dut = self._topToRunTestsOn
        if platform is None:
            platform = VirtualHlsPlatform(**platformKwArgs)
        else:
            assert not platformKwArgs, platformKwArgs

        self.install(platform)

        tc = self.tc
        tc.compileSimAndStart(dut, target_platform=platform)
        BaseIrMirRtl_TC._test_no_comb_loops(tc)
        self._runWithTimeLog(self.TIME_LOG_STAGE.RTL, self.testRtl)

    def test_allInOne_withModel(self,
                    IN_DATA: tuple[Union[PassTestIoIn, Sequence[HConst]], ...],
                    OUT_DATA_REF: Optional[tuple[Union[PassTestIoOut, list[HConst]], ...]]=None,
                    OUT_ITEM_CNT_LIMITS: Optional[tuple[Optional[int], ...]]=None,
                    IO_CONTROL_RANDOMIZE: Optional[tuple[Optional[Optional[bool]], ...]]=None,
                    model: Optional[Callable[[Sequence[HConst], ...], None]]=None,
                    platform:Optional[VirtualHlsPlatform]=None,
                    platformKwArgs=dict(
                        # debugFilter={  # *HlsDebOugBundle.ALL_RELIABLE,
                        # # HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                        # # HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                        # },
                        # llvmCliArgs=[
                        #    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                        #    # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                        #    # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                        # ],
                    ),
                    ):
        """
        :param model: a generator function or normal function which will be used
            to generate reference outputs for input data.
            The names of arguments should match the names of ports on RTL level.
            If None the dut.model is used.
        :param OUT_DATA_REF: optional specification of outputs for additional specification of
            what PassTestIo should be used
        """
        self.initTestOutDataRefUsingModel(IN_DATA=IN_DATA, OUT_DATA_REF=OUT_DATA_REF,
                                          IO_CONTROL_RANDOMIZE=IO_CONTROL_RANDOMIZE,
                                          OUT_ITEM_CNT_LIMITS=OUT_ITEM_CNT_LIMITS, model=model)
        self.test_allInOne(platformKwArgs=platformKwArgs,
                           platform=platform)
