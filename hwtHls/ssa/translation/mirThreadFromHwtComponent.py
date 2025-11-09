from hdlConvertorAst.translate.common.name_scope import NameScope
from hwt.hwModule import HwModule
from hwtHls.llvm.llvmIr import MetadataThreadHwtComponent, IntStringTupleOrObjectPath, Function, \
    HwtHlsIoMetadata, HwtHlsIoMetadata_get, Argument, IODirection
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistChannels
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.abstract.componentBuilder import AbstractComponentBuilder


def _importByPath(name: list[str]):
    """
    Import using list of module names
    http://www.sphinx-doc.org/en/stable/extdev/index.html#dev-extensions
    """

    mod = None
    for i, comp in enumerate(name):
        try:
            # if imported sucessfully __import__ returns a top module
            mod = __import__('.'.join(name[:i + 1]))
        except ModuleNotFoundError:
            for comp in name[1:]:
                try:
                    mod = getattr(mod, comp)
                except AttributeError:
                    raise
    return mod


def IntStringTupleOrObjectPath_toPy(v: IntStringTupleOrObjectPath):
    VT = IntStringTupleOrObjectPath.ValueT
    t = v.valT
    if t == VT.V_NULL:
        return None
    elif t == VT.V_INT:
        return int(v.vInt)
    elif t == VT.V_STR:
        return v.vStr
    elif t == VT.V_TUPLE:
        return tuple(IntStringTupleOrObjectPath_toPy(_v) for _v in v.vTuple)
    elif t == VT.V_OBJECT:
        return _importByPath(v.vObj.value)
    else:
        raise AssertionError("Unknown type of IntStringTupleOrObjectPath", VT)


def mirThreadFromHwtComponentMetadata(
        channels: HlsNetlistChannels,
        hwtCompMd: MetadataThreadHwtComponent,
        toLlvm: ToLlvmIrTranslator,
        toNetlist: HlsNetlistAnalysisPassMirToNetlist,
        F: Function):

    m = _importByPath(hwtCompMd.constructor.value)
    args = tuple(IntStringTupleOrObjectPath_toPy(a) for a in hwtCompMd.constructorArgs)
    kwargs = {aName: IntStringTupleOrObjectPath_toPy(a) for aName, a in hwtCompMd.constructorKwargs}
    ioConnectionOverride = {
        hwIoIndex: IntStringTupleOrObjectPath_toPy(newConnected)
        for hwIoIndex, newConnected in hwtCompMd.ioMappingOverride
    }
    mInstance: HwModule = m(*args, **kwargs)
    for pName, p in hwtCompMd.hwParams:
        p = IntStringTupleOrObjectPath_toPy(p)
        assert hasattr(mInstance, pName), ("Assert that the instance truppy have this parameter before setting it", mInstance, pName)
        setattr(mInstance, pName, p)

    netlist = toNetlist.netlist
    parentHwModule: HwModule = netlist.parentHwModule
    instanceName = NameScope.RE_NON_ID_CHAR.sub("_", F.getName().str())
    instanceName = AbstractComponentBuilder(parentHwModule, None, netlist.namePrefix)._findSuitableName(instanceName)
    setattr(parentHwModule, instanceName, mInstance)
    ioMds: list[HwtHlsIoMetadata] = HwtHlsIoMetadata_get(F)
    for argI, (arg, ioMd) in enumerate(zip(F.args(), ioMds)):
        arg: Argument
        ioMd: HwtHlsIoMetadata
        insideIoPath = ioConnectionOverride.get(argI)
        if insideIoPath is None:
            ioInside = getattr(mInstance, arg.getName().str())
        else:
            raise NotImplementedError()

        if ioMd.otherThreadFn is None:
            ioOutside, _, _, _, _, _, _ = toLlvm.ioSorted[ioMd.otherArgIndex]
        else:
            # based on HlsNetlistAnalysisPassMirToNetlistLowLevel.__init__
            if ioMd.direction == IODirection.IO_DIR_IN:
                channelKey = (ioMd.otherThreadFn, ioMd.otherArgIndex, F, argI)
            else:
                channelKey = (F, argI, ioMd.otherThreadFn, ioMd.otherArgIndex)
            c = channels._channelsBetweenLlvmThreadsMir.get(channelKey)
            if c is None:
                # add new record about channel if this is first seen access to the channel
                channels._channelsBetweenLlvmThreadsMir[channelKey] = ioInside
                channels._channelsBetweenLlvmThreads[ioInside] = (None, None)
                continue  # no connection required as ioInside will be directly used
            else:
                if c._parent is None:
                    # c current channel HwIo is just placeholder,
                    # replace it with this
                    r, w = channels._channelsBetweenLlvmThreads.pop(c)
                    if r is not None:
                        r: HlsNetNodeRead
                        assert r.src is None
                        assert isinstance(r, (HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge)), r
                        assert w.scheduledZero is None, r
                        netlist = r.netlist
                        # convert HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge -> HlsNetNodeRead
                        newR = HlsNetNodeRead(netlist, r.ioProxy, ioInside, r._portDataOut._dtype,
                                              r.name, r.channelInitValues)
                        if not r._isBlocking:
                            newR.setNonBlocking()
                        builder: HlsNetlistBuilder = netlist.getHlsNetlistBuilder()
                        builder._addNode(newR)

                        builder.replaceOutputsOfHlsNetNodeRead(r, newR)
                        builder.replaceInputsOfHlsNetNodeRead(r, newR)
                        builder._assertNodeIsDisconnected(r)
                        r.markAsRemoved()

                    if w is not None:
                        w: HlsNetNodeWrite
                        assert w.dst is None
                        assert isinstance(w, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)), w
                        assert w.scheduledZero is None, w
                        netlist = w.netlist

                        # convert HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge -> HlsNetNodeWrite
                        newW = HlsNetNodeWrite(netlist, w.ioProxy, ioInside, w._mayBecomeFlushable, w.name, bufferCapacity=w._bufferCapacity)
                        if not w._isBlocking:
                            newW.setNonBlocking()
                        builder: HlsNetlistBuilder = w.getHlsNetlistBuilder()
                        builder._addNode(newW)

                        builder.replaceOutputsOfHlsNetNodeWrite(w, newW)
                        builder.replaceInputsOfHlsNetNodeWrite(w, newW)
                        builder._assertNodeIsDisconnected(w)
                        w.markAsRemoved()

                    channels._channelsBetweenLlvmThreads[ioInside] = (r, w)
                    channels._channelsBetweenLlvmThreadsMir[channelKey] = ioInside
                    continue  # no connection required as ioInside would be directly used
                else:
                    # the interface is phisycally constructed and we should connect to it
                    ioOutside = c

        if ioMd.direction == IODirection.IO_DIR_IN:
            src = ioOutside
            dst = ioInside
        else:
            assert ioMd.direction == IODirection.IO_DIR_OUT
            src = ioInside
            dst = ioOutside
        dst(src)
