from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t


def abcCmd_resyn2(net: Abc_Ntk_t):
    # abc standard scripts
    # resyn2      "b; rw; rf; b; rw; rwz; b; rfz; rwz; b"
    # with replaced https://github.com/YosysHQ/yosys/issues/4039
    #   rf -> drf,-l
    #   rw -> drw,-l
    net = net.Balance()
    net = net.DRewrite(fUpdateLevel=True)
    net = net.DRefactor(fUpdateLevel=True, fExtend=True)
    net = net.Balance()
    net = net.DRewrite(fUpdateLevel=True)
    net = net.DRewrite(fUpdateLevel=True, fUseZeros=True)  # rewrite -z
    net = net.Balance()
    net = net.DRefactor(fUpdateLevel=True, fUseZeros=True, fExtend=True)  # refactor -z
    net = net.DRewrite(fUpdateLevel=True, fUseZeros=True)  # rewrite -z

    net.Rewrite(fUpdateLevel=True, fUseZeros=True)  # hwtHls specific
    net.Refactor(fUpdateLevel=True)  # hwtHls specific
    net = net.Balance()

    return net


def abcCmd_compress2(net: Abc_Ntk_t):
    # abc standard scripts
    # compress2   "b -l; rw -l; rf -l; b -l; rw -l; rwz -l; b -l; rfz -l; rwz -l; b -l"
    # with replaced https://github.com/YosysHQ/yosys/issues/4039
    #   rf -> drf,-l
    #   rw -> drw,-l
    net = net.Balance(fUpdateLevel=False)  # balance -l
    net = net.DRewrite(fUpdateLevel=False)  # rewrite -l
    net = net.DRefactor(fUpdateLevel=False, fExtend=True)
    net = net.Balance(fUpdateLevel=False)  # balance -l
    net = net.DRewrite(fUpdateLevel=False)  # rewrite -l
    net = net.DRewrite(fUseZeros=True, fUpdateLevel=False)  # rewrite -z -l
    net = net.Balance(fUpdateLevel=False)  # balance -l
    net = net.DRewrite(fUseZeros=True, fUpdateLevel=False)  # rewrite -z -l
    net.Rewrite(fUpdateLevel=False)  # hwtHls specific
    net.Refactor(fUpdateLevel=False)  # hwtHls specific
    net = net.Balance(fUpdateLevel=False)  # balance -l

    return net
