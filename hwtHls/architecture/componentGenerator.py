from io import StringIO

from hwt.hwModule import HwModule
from hwt.pyUtils.setList import SetList
from hwt.serializer.store_manager import SaveToStream
from hwt.synth import to_rtl


class HlsErrorHighlyInefficientImplementation(Exception):
    """
    Exception raised when component is configured in highly inefficient configuration.
    """
    pass


class ComponentGenerator():
    """
    Base class for object responsible for hardware realization of operator/intrinsic function.
    It provides info for scheduler, lowering methods and hardware realization.
    There are several different ways how to convert MIR instruction to a final hardware
    for more details see methods of this class.

    :attention: ComponentGenerator may instantiate new HwModule. 
        But there are several limitations for synchronization of components
        which can be connected into pipelines without rewrite of synchronization logic.
        * There can not be any comb path from any input to any output. This implies:
            * Ready signal must be always driven from register. Inputs can not have ready at all.
            * There can be just a single output with ready.
            * Output ready must be driven from const 1 if component time is less than 1 clk period.
        * Input must be acceptable in the same clock when output is produced. Because input has no ready
          and valid of output marks that the component has finished its job and is ready for new input.
        * If component fits into a single clock no output must not have ready or valid,
          input must not have ready and may have valid.
          This is important to prevent combinational loop on sync of for components where input
          and output are part of same HandshakeSyncNode
    
    Expected parameters of circuit for Function units
        * no combinational loops on io signals
        * no register duplication in this unit or in parent user
        * minimal latency, 0-delay 
    :note: Merging child and parent loop is done by PyBytecodeLoopFlattenUsingIf
    :note: If input is of HStructDataVld and output of HStructDataRdVld it means
        that the ready for input must be actually handled by parent user.
        This is typically through flag which marks occupation of pipeline stage.
        Or it is done implicitly trough the latency of pipeline or delay in FSM.
        
    Programs like this can not accept read and perform write in a single clock cycle.
    .. code-block::python
        while True:
            x = read()
            for _ in hwrange(n):
                ...
            write(x)

    This is because this transforms to a loop like this and i can not equal 0 and last at once.
    .. code-block::python
        while True:
            for i  in hwrange(n):
                if i == 0:
                    x = read()
                ...
                if i == last:
                    write(x)

    There are several equivalent forms of this code e.g.:
    .. code-block::python
        while True:
            x = read(blocking=False)
            if x.valid:
                for _ in hwrange(n):
                    ...
                write(x)
    Which is equivalent to (after PyBytecodeLoopFlattenUsingIf)
    .. code-block::python
        
        while True:
            for i in hwrange(n):
                if i == 0:
                    while True:
                        x = read(blocking=False)
                        if x.valid:
                            break;
                ...
                if i == last:
                    write(x)

    
    This is a problem for non-stalling pipelines. There must be an additional register for the input.
    Problem 1 - sync. comb. loops in user of this: If the input and output are mapped into same pipeline stage,
      special care must be taken to mark that output should never wait for input to be available (and also the reverse).
      Otherwise the pipeline would just stall as the output can not be provided if input was never enabled.
      There is also an additional issue related to a case where there are multiple such units are instantiated in a single pipeline stage.
      Each port of the unit needs to be in correct synchronization island.
    Problem 2 - input can not have ready: There is an additional issue with synchronization. The ready+valid may be used only for output.
      But the ready for output does not imply the ready for input. (It happens in next clock cycle).
    Problem 3 - extra registers: Problems 1,2 can be solved by extra registers for input, but this practically doubles the register consumption.
      
    The loop may be rotated.
    .. code-block::python
        while True:
            xVld = False
            if xVld:
                for i  in hwrange(n):
                    ...
            write(x)
            x = read()
            xVld = True
    
    This code will be transformed into for-loop with body speculated.
    .. code-block::python
        while True:
            xVld = False
            for i  in hwrange(n):
                ...
                if i == last:
                    if xVld:
                        write(x)
                        x = read()
                        xVld = True
    
    This solves problem 2 but it creates a new problem.
    Problem 4 - unintended eval of body: This adds full latency of the loop as a delay for a case of first run.
        This also requires write to be flushable.
        It is not simple to resolve that loop iterations will be just nop and only the last one will read x
    
    .. code-block::python
        while True:
            x = read()
            for i  in hwrange(n):
                ...
                if i == last:
                    write(x)
                    x = read()
    
    This solves problem 1,2,3,4 but there are 2 potential reads of x
    It may be hard to prove that these two may never happen at once and
    thus they can be mapped into same clock cycle.
    * This generates 2 ArchElements which must share input port.
      The selection bits is actually the state of the the main loop
    
    :note: This form has the problems 3 (extra regs for x).
    .. code-block::python
        while True:
            for i  in hwrange(n):
                if i == 0:
                    x = read()
                ...
                if i == last:
                    write(x)
                    x = read()

    .. code-block::python
        while True:
            for i  in hwrange(n):
                if i == 0:
                    x = read()
                ...
                if i == last:
                    write(x)
                    x = read()

    :note: This form duplicates register for output,
        but the duplicated register may be merged to register used during loop iteration
        if there is any. 
      * input - HStructDataVld
      * output - HStrctDataRdVld, needs flushing
    .. code-block::python
        outVld = False
        while True:
            for i  in hwrange(n):
                if i == 0:
                    if outVld:
                        write(x)
                    x = read()
            outVld = True
    
    Working and optimal cases are:
    1. The loop is fully unrolled and
      * input - HStructDataVld
      * output - HStrctDataRdVld
    .. code-block::python
        while True:
            x = read()
            ...
            write(x)
    
    2. Read and write can happen in the same clock
      * input - HStructDataVld
      * output - HStrctDataRdVld
      * problems: comp path from read.valid to write.valid
    .. code-block::python
        while True:
            x = read()
            for i  in hwrange(n):
                ...
            write(x)
    
    3. Read and write can not happen in the same clock
     * input - HStrctDataRdVld
     * output - HStrctDataRdVld
     * the internal loop must not be pipelined, it must be FSM and the read and
       the write must be in different state to prevent combinational pat from ready of output
       to ready of input
     
    """

    def __init__(self, platform: "DefaultHlsPlatform"):
        self.platform = platform

    def resolveRealizationOfNode_compileToResolveScheduling(self, parentHwModule: HwModule, hwModule: HwModule):
        # :note: store_manager can not be netlist.parentHwModule._store_manager because
        #  the name_scope is currently in parent component body and thus name collisions
        #  will not be handled as they should
        #  and there is a second problem that the output products will not be placed where they should be
        buff = StringIO()
        store_manager = SaveToStream(parentHwModule._store_manager.serializer_cls, buff)
        # store_manager = netlist.parentHwModule._store_manager
        to_rtl(hwModule, store_manager, target_platform=self.platform)
        return store_manager

    def resolveRealizationOfNode(self, node: "HlsNetNode") -> None:
        """
        Get OpRealizationMeta which is used during scheduling.
        """
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__, node)

    def toHwtCompatibleOperatorBeforeScheduling(self, node: "HlsNetNode",
                                                worklist: SetList["HlsNetNode"]):
        """
        Optionally rewrite this to circuit composed of HWT compatible operator nodes
        
        :param node: node to be optionally rewritten
        :param worklist: worklist for all updated nodes, to run lowering recursively and to
            run simplifycations on
        :returns: True if netlist was modified
        """
        return False

    def toHwtCompatibleOperatorAfterScheduling(self, node: "HlsNetNode", worklist: SetList["HlsNetNode"]) -> bool:
        """
        Same functionality as :meth:`toHwtCompatibleOperatorBeforeScheduling` just after netlist was scheduled
        """
        return False

    def toRtlForNode(self, node: "HlsNetNode", allocator: "ArchElement") -> None:
        """
        Translate from HlsNetNode to hwt RTL netlist.

        :attention: this function may mutate properties of node in order to inject generated RLT
        """
        raise NotImplementedError("This method is supposed to be overriden in child class", self.__class__, node)
