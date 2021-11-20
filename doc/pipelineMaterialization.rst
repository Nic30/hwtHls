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
    * https://llvm.org/pubs/2002-12-LattnerMSThesis.pdf
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
