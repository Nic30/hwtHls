"""
Module of translator from Python bytecode to :mod:`hwtHls.ssa`
In general this the conversion is done directly from bytecode and CFG analysis to SSA.
There are several pragma like objects which can be used to customize translation or to access preprocessor directly
from a translated code.
The translation process involves several things.

1. The bytecode CFG is analyzed and loops are detect.
   This is required in advance because we need to know then we resolved every predecessor for a block in SSA construction algorithm.

2. A preprocessor immediately evaluates everything which is not required to convert to circuit.
   This mainly involves operations and variables of non hardware type.
   Instances of SsaValue, HValue, Interface, RtlSignal are hardware objects
   for which operations are not evaluatuable during compilation instead they are staged into output SSA.

   * There is a specific case where predecessor block may disappear or are dynamically added because jumps in code are evaluated in preprocessor
     or some code feature (e.g. loop) is expanded.

   * We also must rename labels in preprocessor expanded loops.

3. Every operation which can not be evaluated in preprocessor needs to be translated to output SSA
   with applied label renaming due to preprocessor caused code expansions.

   * The low level translations are shared with :mod:`hwtHls.frontend.ast` to avoid code duplication.

"""


def hlsBytecode(fn):
    """
    Wrapper which does nothig but parks the function as compatible with bytecode HLS frontend for documentation purposes.
    """
    return fn


def hlsLowLevel(fn):
    """
    Wraper which marks function as integrated in HLS framework of this library. Functions marked with this will recieve
    all arguments as they are without any expansion.
    """
    fn.__hlsIsLowLevelFn = True
    return fn
