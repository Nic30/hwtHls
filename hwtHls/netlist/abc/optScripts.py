from typing import Sequence

from hwtHls.netlist.abc.abcCpp import Abc_Ntk_t, Abc_Obj_t


def Abc_collectPiData(net: Abc_Ntk_t):
    return [pi.Data() for pi in net.IterPi()]


def Abc_updatePiData(net: Abc_Ntk_t, data: Sequence):
    assert len(data) == net.PiNum()
    for d, piNew in zip(data, net.IterPi()):
        piNew: Abc_Obj_t
        piNew.SetData(d)


def abcCmd_resyn2(net: Abc_Ntk_t):
    # abc standard scripts
    # resyn2      "b; rw; rf; b; rw; rwz; b; rfz; rwz; b"
    # backup because Abc_NtkBalance does not preserve object data
    origPiData = Abc_collectPiData(net)
    net = net.Balance()
    net.Rewrite()
    net.Refactor()
    net = net.Balance()
    net.Rewrite()
    net.Rewrite(fUseZeros=True)  # rewrite -z
    net = net.Balance()
    net.Refactor(fUseZeros=True)  # refactor -z
    net.Rewrite(fUseZeros=True)  # rewrite -z
    net = net.Balance()
    Abc_updatePiData(net, origPiData)
    return net


def abcCmd_compress2(net: Abc_Ntk_t):
    # abc standard scripts
    # compress2   "b -l; rw -l; rf -l; b -l; rw -l; rwz -l; b -l; rfz -l; rwz -l; b -l"
    # backup because Abc_NtkBalance does not preserve object data
    origPiData = Abc_collectPiData(net)
    net = net.Balance(fUpdateLevel=False)  # balance -l
    net.Rewrite(fUpdateLevel=False)  # rewrite -l
    net.Refactor(fUpdateLevel=False)
    net = net.Balance(fUpdateLevel=False)  # balance -l
    net.Rewrite(fUpdateLevel=False)  # rewrite -l
    net.Rewrite(fUseZeros=True, fUpdateLevel=False)  # rewrite -z -l
    net = net.Balance(fUpdateLevel=False)  # balance -l
    net.Rewrite(fUseZeros=True, fUpdateLevel=False)  # rewrite -z -l
    net = net.Balance(fUpdateLevel=False)  # balance -l

    Abc_updatePiData(net, origPiData)
    return net
