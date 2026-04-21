"""
This module contains code related to hardware architecture layer of this project.
A hardware architecture is represented by netlist with only :class:`hwtHls.netlist.nodes.archElement.ArchElement` nodes at top level.

:class:`hwtHls.netlist.nodes.archElement.ArchElement` aggregates other HlsNetNodes to a larger chunks
and specifies synchronization scheme for nodes inside.

:note: This module works with already generated architecture from netlist.
    The initial netlist to architecture translation is described in :py:mod:`hwtHls.netlist`

There are several complicated things:
* Architecture type and communication channel implementation significantly affect scheduling.
  * It is up to user to tune up initial parameters or to write a design space search loop. This module
   does not do rescheduling.
* Nodes which are crossing clock boundaries and nodes with internal structure or custom synchronization type.
  * The synchronization is allocated per clock window. The problem is that node may span more than 1 clock cycle.
    (for example BRAM read, DSP48E1 block etc.) Offten we can not simply cut nodes to pieces because of complex internal structure.
    Parts of node may be in a different ArchElement. Various types of nodes with complex internal hierarchy and internal synchronization
    behavior are hard to analyze and to map into arbitrary parent circuit implemented by ArchElement instance.
  * Nodes are cut on clock window boundaries by :class:`hwtHls.netlist.transformation.multiClockNodeSplit.HlsNetlistPassMultiClockNodeSplit`
* Optional reads/writes and non analyzable FSMs.
  * For some ArchElements it is impossible to determine latency between IO channels.
    This implies that it is impossible to determine the ideal size for data buffers which are connected in parallel with this element.
    This may result in degraded performance or deadlock.
* Problems related to handshake loops. 
  * There are numerous cases when combinational loop in handshake synchronization appear. If this is the case the circuit synchronization
    must be rewritten to an acyclic form.
  * Handshake loops are removed in :class:`hwtHls.architecture.transformation.syncLowering.HlsArchPassSyncLowering`
* Flushing behavior.
  * During optimizations back pressure, ArchElement merging or rescheduling may result in some IO operations to be performed only together.
    The original IO order must be taken in account when implementing sync of ArchElement.
  * Flushing logic is generated in :class:`hwtHls.architecture.transformation.syncLowering.HlsArchPassSyncLowering`
* Communication asynchronous to FSM state. It is offten the case that some registers in FSM must be modified
  independently on FSM state. For example some loop state which is partly mapped to FSM may be restarted externaly from outside
  of FSM or from state where it is modified trough IMMEDIATE channels. 


Register allocation:
:see: Basic of register allocation https://pages.cs.wisc.edu/~horwitz/CS701-NOTES/5.REGISTER-ALLOCATION.html
      RA for exclisively executed blocks https://dl.acm.org/doi/pdf/10.1145/37888.37920
      llvm::RegAllocPBQP uses "Linear Scan Register Allocation" by Poletto and Sarkar https://web.cs.ucla.edu/~palsberg/course/cs132/linearscan.pdf
      Optimal Polynomial-Time Interprocedural Register Allocation for High-Level Synthesis Using SSA Form 
          https://www.epfl.ch/labs/lap/wp-content/uploads/2018/05/BriskMay07_OptimalPolynomialTimeInterproceduralRegisterAllocationForHighLevelSynthesisUsingSsaForm_IWLS07.pdf

In traditional register allocation we need to know all registers in advance to compute live ranges
and then we can compute register mapping as a graph coloring.
There the situation is slightly different.
There is no register spiling and all registers will have to be mapped to some FF.
Traditionaly registes/variables are of n-bits but physical FFs are just 1b
That means that the number of FFs required is max number of register bits in any state
and we need only to pick a mapping of registers/variables to FFs which have least scrambling
to improve readablitity.
The :class:`LoopChanelGroup` objects connected to block/loop on same place are known to be exclusive,
that means that they may be mapped to same register, except for control registers (vld/full for channels). 

Register allocation is split to 2 phases:
Before scheduling RA:
  * FSMs convert channels to register writes,
    share registers for exclusively written backedges/forwardedges. 
After scheduling RA:
  * AsapCompact for bitwidth reducing instructions
  * AlapCompact for bitwidth increasing  instructions
  * :note: that performing RA for every register yields no benefit for tightly packed clock windows on FPGA
     as the additional MUXes would increase latency and FFs are fixed parts of CLBs.

"""
