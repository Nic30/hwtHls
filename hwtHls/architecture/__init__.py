"""
This module contains code related to hardware architecture layer of this project.
A hardware architecture is represented by netlist with only :class:`hwtHls.netlist.nodes.archElement.ArchElement` nodes at top level.
:class:`hwtHls.netlist.nodes.archElement.ArchElement` aggregates other HlsNetNodes to a larger chunks
and specifies synchronization and data exchange channels between these elements.

:note: This module works with already generated architecture from netlist. The initial netlist to architecture translation is described in :mode:`hwtHls.netlist`

There are several complicated things:
* Nodes which are crossing clock boundaries and nodes with internal structure or custom synchronization type.
  * The synchronization is allocated per clock cycle. The problem is that node may span more than 1 clock cycle
    (for example BRAM read, DSP48E1 block etc.) Often we can not simply cut nodes to pieces because of complex internal structure.
    Parts of node may be in a different ArchElement. Various types of nodes with complex internal hierarchy and internal synchronization
    behavior are hard to analyze and to map into arbitrary parent circuit implemted by ArchElement instance.
* Optional reads/writes and non analyzable FSMs.
  * For some ArchElements it is impossible to determine latency between IO channels.
    This implies that it is impossible to determine the ideal size for data buffers which are connected in parallel with this element.
    This may result in degraded performance or deadlock.
* Problems related to handshake loops. 
  * There are numerous cases when combinational loop in handshake synchronization appear. If this is the case the circuit synchronization
    must be rewritten to an acyclic form.
* Flushing behavior.
  * During optimizations back pressure, ArchElement merging or rescheduling may result in some IO operations to be performed only together.
    The original IO order must be taken in account when implementing sync of ArchElement.
"""
