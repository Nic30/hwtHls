from io import StringIO
from typing import Dict, Optional

from hdlConvertorAst.to.verilog.verilog2005 import ToVerilog2005
from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.arrayQuery import grouper
from hwt.serializer.verilog.ops import ToHdlAstVerilog_ops
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut


def netlistDebugExpr(o: HlsNetNodeOut, tmpVars:Optional[Dict[HlsNetNodeOut, int]]=None):
    """
    Stringify HlsNetlist expression for debug purposes
    
    :note: tmpVars can be used to share variable numbering between multiple calls of this function
    """
    if tmpVars is None:
        tmpVars: Dict[HlsNetNodeOut, int] = {}
    exprOut = StringIO()
    _netlistDebugExpr(o, tmpVars, exprOut)
    res = [f"v{i} = {v}" for v, i in sorted(tmpVars.items(), key=lambda x: x[1])]
    res.append(exprOut.getvalue())
    return "\n".join(res)


def _netlistDebugExpr(o: HlsNetNodeOut, tmpVars: Dict[HlsNetNodeOut, int], exprOut: StringIO):
    n = o.obj
    if isinstance(n, HlsNetNodeOperator):
        op = n.operator
        if op == AllOps.TERNARY:
            first = True
            if len(n.dependsOn) == 1:
                exprOut.write("copy(")
                _netlistDebugExpr(n.dependsOn[0], tmpVars, exprOut)
                exprOut.write(")")
            else:
                for v, c in grouper(2, n.dependsOn, padvalue=None):
                    if c is not None:
                        _netlistDebugExpr(v, tmpVars, exprOut)
                        if first:
                            first = False
                            exprOut.write(" if ")
                        else:
                            exprOut.write(" elif ")
                        _netlistDebugExpr(c, tmpVars, exprOut)
                    else:
                        exprOut.write(" else ")
                        _netlistDebugExpr(v, tmpVars, exprOut)
        else:
            hdlOp = ToHdlAstVerilog_ops.op_transl_dict[op]
            iCnt = len(n._inputs)
            if iCnt == 1:
                opStr = ToVerilog2005.GENERIC_UNARY_OPS[hdlOp]
                exprOut.write(opStr)
                _netlistDebugExpr(n.dependsOn[0], tmpVars, exprOut)
            elif iCnt == 2:
                opStr = ToVerilog2005.GENERIC_BIN_OPS[hdlOp]
                exprOut.write("(")
                _netlistDebugExpr(n.dependsOn[0], tmpVars, exprOut)
                exprOut.write(opStr)
                _netlistDebugExpr(n.dependsOn[1], tmpVars, exprOut)
                exprOut.write(")")
            else:
                raise NotImplementedError()

    else:
        v = tmpVars.get(o, None)
        if v is None:
            v = tmpVars[o] = len(tmpVars)
        exprOut.write(f"v{v}")
