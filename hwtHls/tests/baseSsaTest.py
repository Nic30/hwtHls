from io import StringIO
import os

from hwt.synthesizer.unit import Unit
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.transformation.extractPartDrivers import SsaPassExtractPartDrivers
from hwtHls.ssa.transformation.runFn import SsaPassRunFn
from hwtHls.ssa.transformation.removeTrivialBlocks import SsaPassRemoveTrivialBlocks
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtLib.examples.base_serialization_TC import BaseSerializationTC


class TestFinishedSuccessfuly(BaseException):

    @classmethod
    def raise_(cls, *args):
        raise cls(*args)


class BaseSsaTC(BaseSerializationTC):
    """
    :attention: you need to specify __FILE__ = __file__ on each subclass to resolve paths to files
    """

    def tearDown(self):
        self.rmSim()

    def _runTranslation(self, unit_cls, ssa_passes):
        self.rmSim()
        with self.assertRaises(TestFinishedSuccessfuly):
            self.compileSimAndStart(unit_cls, target_platform=VirtualHlsPlatform(ssa_passes=ssa_passes))
        self.rmSim()

    def _test_ll(self, unit_constructor: Unit):
        buff = StringIO()
        ssa_passes0 = [
            SsaPassConsystencyCheck(),
            SsaPassDumpToLl(buff),
            SsaPassRunFn(TestFinishedSuccessfuly.raise_)
        ]
        unit = unit_constructor()
        self._runTranslation(unit, ssa_passes0)
        ll = buff.getvalue()
        buff.truncate(0)
        buff.seek(0)
        self.assert_same_as_file(ll, os.path.join("data", unit.__class__.__name__ + "_0.ll"))

        ssa_passes1 = [
            SsaPassRemoveTrivialBlocks(),
            SsaPassConsystencyCheck(),
            SsaPassDumpToLl(buff),
            SsaPassRunFn(TestFinishedSuccessfuly.raise_)
        ]
        unit = unit_constructor()
        self._runTranslation(unit, ssa_passes1)
        ll = buff.getvalue()
        buff.truncate(0)
        buff.seek(0)
        self.assert_same_as_file(ll, os.path.join("data", unit.__class__.__name__ + "_1.ll"))

        ssa_passes2 = [
            SsaPassRemoveTrivialBlocks(),
            SsaPassExtractPartDrivers(),
            SsaPassConsystencyCheck(),
            SsaPassDumpToLl(buff),
            SsaPassRunFn(TestFinishedSuccessfuly.raise_)
        ]
        unit = unit_constructor()
        self._runTranslation(unit, ssa_passes2)
        ll = buff.getvalue()
        buff.truncate(0)
        buff.seek(0)
        self.assert_same_as_file(ll, os.path.join("data", unit.__class__.__name__ + "_2.ll"))
