"""
For if/switch statement each branch is always performed but it may be swithed to perform no operation.
This means that the body of the branch is not performed if it should not but the control always token passes trough that branch.
This means that every node behind menitioned if-statement will recieve synchronization token from all predecessors.
Thus synchronization must simply wait on every input to be present.
However this does not work for loops where the loop end is predecessor of the loop entrance.
This results in deadlock on first iteration.
doi: 10.1109/MCAS.2021.3071631 solves this problem using eager forks which allow to pass some data in advance.
However this method does not solve all issues and for some cases is significantly more complex than required.

There are 8 cases of loops where synchronization has to be handled differently,
which are explained in following section.

Dictionary of terms for this section:
    * https://www.cs.cornell.edu/courses/cs6120/2020fa/lesson/
    .. code-block:: C

              for (int i=0;i<8;i++) {
                  // i is induction variable
                  // i++ is induction step
                  i_next = i + 1 // derived induction variable
                  X[i_next] = X[i]*10; // loop body
              }
              // loop end/code after loop

    * IMT - Independent multithreading, parallelization techniques which removes dependencies between the loop iterations
            and then run some iterations in parallel
        * induction variable elimination - if the pattern of induction variable update is known, it is possible
          to precompute it for next iteration without waitin on the end of iteration
        * reduction - if the loop performs some reduction (cummulative associative) it is possible to compute it divide and conqure maner
    * CMT - Cyclic multithreading, parallelization techniques for non-removable loop-carried dependencies
       * e.g. HELIX https://doi.org/10.1145/2259016.2259028
            * detect synchronization needed for code blocks, perform code after all requirements met from other threads
    * PMT - pipelined multithreading
       * e.g. decoupled software pipelining (DSWP) https://doi.org/10.1109/PACT.2004.1342552
            * generates pipeline stages by finding strongly connected components in the program dependence graph (PDG),
              a graph combining both data and control dependences.
    * (loop carried) data dependency means that the next iteration requires result of previous iteration
        * forms of data dependencies:
            * none
            * static - the write in current loop affects next iterations in statically predictable way

                .. code-block:: C

                    for (int i=0;i<8;i++) {
                        X[i+1] = X[i]*10;
                    }

            * dynamic - the write in current loop affect next iterations in unpredictable way and potential data
                        collision must be handled dynamically depending on program inputs

                .. code-block:: C

                    for (int i=0;i<8;i++) {
                        X[Y[i]] = X[i]*10;
                    }

        * types of data dependencies
            * RAW read-after-write
            * WAR write-after-read
            * WAW write-after-write
            * RAR read-after-read is important only for streams, because the order of data from stream must be guaranted

        * can be detected by looking if code uses same symbol as input and output

    * control dependecy means that the body may trigger loop break/continue or iteration condition depends
      on data from previous iteraton
        * can be detected by non constant iteration step or by conditional break in loop body

    * variable latency means that the latency of body may change or is different between the branches in loop body
        * can be infered from latency of branches of code and the latency of IO

    * Traditional loop optimizations:
        * code motion: precompute all invariant code (which does not change output) before loop
        * induction variable reductions
        * unswitching https://www.cs.cornell.edu/courses/cs6120/2019fa/blog/loop-unswitching/

            .. code-block:: c

                for (int i = 0; i < 100; ++i) {
                    if (c) {  // Loop-invariant value.
                        f();
                    } else {
                        g();
                    }
                }

                // Becomes:

                if (c) {
                    for (int i = 0; i < 100; ++i) {
                        f();
                    }
                } else {
                    for (int i = 0; i < 100; ++i) {
                        g();
                    }
                }

        * permutation: swap the loops in hierarchy of nested loops
        * unrolling: increase loop step and perform several steps at once
        * fusion: merge loops if iteration scheme and dependencies allows for that
        * fission
        * coalesing: coalesce nested loops into a single loop without affecting the loop functionality
        * peeling: carving off the first few iterations of the loop and running them separately, leaving you with a simpler main loop body
        * polyhedral and interchange, tiling optimizations: changes style of iteration
        * Super-word level parallelism (SLP)

    * Traditional expression optimizations:
        * partial redundancy elimination (PRE)
            .. code-block:: c

                if (some_condition) {
                    // some code that does not alter x
                    y = x + 4;
                } else {
                    // other code that does not alter x
                }
                z = x + 4;

                // Becomes:
                if (some_condition) {
                    // some code that does not alter x
                    t = x + 4;
                    y = t;
                } else {
                    // other code that does not alter x
                    t = x + 4;
                }
                z = t;


The case specification corresponds to a tuple: (data dependency, control dependency, variable latency)

0. n,n,n: Straight pipeline without any extra sync needed.
    .. code-block:: C

        while (1) {
            Y.write(X.read();
        }

1. n,n,y: Use tagging to detect order of outputs. The branches are executed non speculatively in order.
    Just the input from predecessors may come with a different latency.
    Assign modulo counter value on iteration start, on each IO and end of loop wait for that id.

    .. code-block:: C

        while (1) {
            int tmp = X.read();
            if (tmp)
                tmp = long_op(tmp);
            Y.write(tmp);
        }

2. n,y,n: The pipeline must stall on each dependency or partially performed iterations in pipeline must canceled
        and executed from beginning or speculatively performed in advance and then applied once the control flow is confirmed.
         (= stalling or parallel speculation or restarting.)
         (All IO must wait until the brach speculation is confirmed. Because of this we need to read input
         but not consume it. We should consume only once branch speculation is confirmed to prevent data lose
         for streams.)

    .. code-block:: C

        while (1) {
            int tmp = X.read();
            Y.write(tmp);
            if (tmp)
                break;
        }

3. n,y,y: Tagging + stalling or speculation or restarting (n,n,y + n,y,n)
          (IO synchronization realized by explicit confirmation as in n,y,n and ordering by tagging as in n,n,y. )

    .. code-block:: C

        while (1) {
            int tmp = X.read();
            if (tmp)
                tmp = long_op(tmp);
            Y.write(tmp);
            if (tmp)
                break
        }


4. y,n,n: The data could be just forwarded from next stage in pipeline, depending on time difference of first use and last
         write for a variable this may require some waiting until data is available.

    .. code-block:: C

        int res = 0;
        while (1) {
            res += X.read();
            if (res == 10)
               res = 0;
        }

5. y,n,y: If nature of operations allows it (small enough latency, associative/cumulative op.) it is possible
         to construct a logic for speculation, otherwise the next iteration must wait on result of previous iteration.

    .. code-block:: C

        int res = 0;
        while (1) {
            res += X.read();
            if (res == 10)
               res = long_op(tmp);
        }

6. y,y,n: Same condition for speculation/waiting as in y,n,y. But the next itrations can be executed in advance if data dependency allows it.
         but the iteration result must not be applied unless its confirmed. If this variable latency happens because of IO it may be required
         to use cache/LSU to track on-cly transactions


    .. code-block:: C

        int res = 0;
        while (1) {
            int tmp = X.read();
            res += tmp;
            if (res == 10)
               break;
        }

7. y,y,y: The same as y,n,y and y,y,n plus the code after the loop also has to potentially wait on last iteration or be executed speculatively.

    .. code-block:: C

    .. code-block:: C

        int res = 0;
        while (1) {
            int tmp = X.read();
            res += tmp;
            if (res == 10)
               res = long_op(tmp);
               break;
        }

* Summarization:
    * data/control dependencies can be solved using:
        * forwarding: if the data is already available in the pipeline it can be just bypasses to a place where it is used.
        * stalling: if the domain of possible data would be too high and speculation or restarting would be too costly
        * restarting (speculative serial execution): if the probability of modification of variable si small, it is efficient to perform the dependent code and cancel
            the execution if the variable did not end up in predicted state.
        * speculative parallel execution: If the domain of possible values is small enough or the control branches are already present and idle.
        * All variants can be specified by a max degree of paralel speculative executions and max degree of speculation depth.
            * Forwarding is used naturally if possible
            * otherwise stalling is used when speculation paralelism is 1 and depth is 0
            * speculative serial execution if speculation paralelism is 1 and depth is >0, etc
        * traditional methods
            * Statically scheduled FSM
            * Scoreboard: no register renaming, limited out‐of‐order
            • Tomasulo (reservation stations - implicit renaming, extender register file - explicit renaming): copy‐based register renaming, full out‐of‐order
    * variable latency of internal sections of single pipeline is not problematic, but if the pipeline has some branching
      the output order from pipelines may come in statically unpredictable order.
      This issue can be solved by tagging, tagging assignes a sequential number to each input and output waits
      to a sorted sequece of outptus. This paradigma can be extended to arbitrary number of code branches.
      This however work only for a code segments without internal data/control dependencies.
      (The tagging is used to reconstruct a sequential access to a variables with dependencies.)
      The tagging also can be nesed and is compatible with stalling/speculation/restarting.
    * The restrictions on read/write to IO is described in :mod:`hwtHls.hlsStreamProc.ioGateMaterialization`.

* The thing we want is that pipelined bodies of loops have enough input data to fill whole pipeline.
  But this may generate a secondary problem with data/control collisions.
  The capacity of pipeline corresponds to lenght of loop body plus the latency of IO.
  We do have a capacity specified for pipeline and pipeline code itself.

* Some loop bodies are actually build to concurrently process more than just one transaction.
   * That imples that the counter should be used instead of just a flag for forwarding.
* The operations must be performed in original code order.
    * That means that the for example the next iteration of the cycle has to be performed before
      next intial iteration of the cycle from new start of the program.
    * For a simple structured code it is easy to check because we know exactly which input is
      the input into loop. But is this the case for arbitrary code.

    * Typicaly a node which handles condition of while statement is a gateway to a body of the loop
      but also a gateway into a section behind the loop. The gateways to these nodes are outputs of this node.
      It has also possibly more inputs from the code before (which will execute this loop) and input
      from each break/continue/end of the loop from the body of the loop.
      The data from these inputs may arrive in an order different from original. Because latency of branches
      may be nondeterministic.
"""
from typing import List, Set, Tuple

from hwt.code import If
from hwt.synthesizer.unit import Unit
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.hlsStreamProc.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.toHwtHlsNetlist import SsaToHwtHlsNetlist
from hwtHls.netlist.codeOps import HlsWrite, HlsRead
from hwtHls.netlist.toGraphwiz import HwtHlsNetlistToGraphwiz
from hwtLib.handshaked.builder import HsBuilder
from hwtSimApi.utils import freq_to_period


class SsaSegmentToHwPipeline():
    """
    We know the variables which are crossing pipeline boundary
    from out_of_pipeline_edges and edge_var_live.
    These variables usually appear because of cycle which means
    that there could exists a code section which uses the value from a previous cycle iterration
    and a section which uses a newly generate value.
    This means that a single variable may appear in multiple versions even if it is written only once.
    The cycle may be entered only on a single place (header, because of structured programing).
    However the cycle may be entered from a multiple places and exited to multiple places.
    Which means that the value of variables alive on such a transitions can potentially
    come from multiple places.
    We can potentially instantiate buffers on every path. This however leads to resource wasting.
    Instead we want to output the variable value as soon as we are sure that variable will be consummed.
    This means that we need to walk the blocks instruction by instruction and resolve where the value
    from a previous cycle should be used and where new value may be mixed in or used exclusively.
    On each place where multiple values may appear due to branching we need to add multiplexer
    and use it in following expressions.


   :ivar parent: an Unit instance where the circuit should be constructed
   :ivar freq: target clock frequency
    """

    def __init__(self, parent: Unit, freq: float):
        self.parent = parent
        self.freq = freq

    def _construct_pipeline(self,
                            start: SsaBasicBlock,
                            pipeline: List[SsaBasicBlock],
                            out_of_pipeline_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]],
                            edge_var_live: EdgeLivenessDict):
        """
        :param pipeline: list of SsaBasicBlocks (represents DAG if out_of_pipeline_edges are cut off) to build the pipeline from

        :param start: a block where the program excecution starts
        :param out_of_pipeline_edges: a set of connections between block where pipeline should be cut in order to prevent cycles
            the data channels for this type of connections are added in post processing and are not part of scheduling
        :param edge_var_live: dictionary of variables which are alive on a specific edge between blocks
        :attention: it is expected that the blocks in pipeline are sorted in topological order
            it is important that the outputs from previous block are seen before inputs from previous block
            otherwise the input is threated as an input of pipeline instead of connection between stages in pipeline
        """
        parent = self.parent
        freq = self.freq

        hls: HlsPipeline = HlsPipeline(parent, freq).__enter__()

        toHlsNetlist = SsaToHwtHlsNetlist(hls, start, out_of_pipeline_edges, edge_var_live)
        try:
            toHlsNetlist.io.init_out_of_hls_variables()
            # construct nodes for scheduling
            for block in pipeline:
                toHlsNetlist.to_hls_SsaBasicBlock(block)
            toHlsNetlist.io.finalize_out_of_pipeline_variable_outputs()
        finally:
            # recover from HlsPipeline temporary modification of hls.parentUnit
            hls.parentUnit._sig = hls._unit_sig

        assert not hls.coherency_checked_io
        hls.coherency_checked_io = toHlsNetlist.io._out_of_hls_io

        # [debug]
        to_graphwiz = HwtHlsNetlistToGraphwiz("top")
        with open("top_p.dot", "w") as f:
            to_graphwiz.construct(hls.inputs + hls.nodes + hls.outputs)
            f.write(to_graphwiz.dumps())

        hls.synthesise()

        if toHlsNetlist.start_block_en is not None:
            # the start_block_en may not be pressent if the code is and infinite cycle
            start_init = parent._reg(f"{start.label}_init", def_val=1)
            toHlsNetlist.start_block_en.vld(start_init)
            toHlsNetlist.start_block_en.data(1)
            If(toHlsNetlist.start_block_en.rd,
               start_init(0),
            )

        for (dst_read, src_write), (src_block, dst_block) in toHlsNetlist.io.out_of_pipeline_edges_ports:
            # connect islands and loops in pipeline together
            # handles controll and data (in separate channels)
            src_write: HlsWrite
            dst_read: HlsRead
            dst_t = dst_read.scheduledInEnd[0]
            src_t = src_write.scheduledInEnd[0]
            assert dst_t <= src_t, ("This was supposed to be backward edge", src_write, dst_read)
            # 1 register at minimum, because we need to break a comibnational path
            # the size of buffer is derived from the latency of operations between the io ports
            reg_cnt = max((src_t - dst_t) / freq_to_period(freq), 1)
            channel_init = ()
            # channel_init = ((0,),)
            if toHlsNetlist.start_block_en is None:
                if dst_block is start:
                    # fill channel with sync token with reset values for input variables
                    channel_init = ((1,),)
                    # reg_cnt = 4

            buffs = HsBuilder(parent, src_write.dst,
                              f"hls_backward_{src_block.label:s}_{dst_block.label:s}")\
                .buff(reg_cnt, latency=(1, 2), init_data=channel_init)\
                .end
            dst_read.src(buffs)

