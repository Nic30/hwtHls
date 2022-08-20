"""
Hls circuit netlist used for scheduling and architectural features extraction.
This netlist is usually generated from LLVM MIR but it can be also constructed manually and the netlist itself
does not depends on any object from LLVM MIR.

The netlist is composed of node instances :mod:`hwtHls.netlist.nodes` which do have input/output ports
which can be connected together. One output may have N connected inputs. Input may have at most 1 output connected.
The connection information is stored in node properties and can be accessed from bout directions (src->dst, dst->src).



"""
