from math import ceil
from typing import Type, Union

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.hwIOStruct import HwIOStructVld, HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.code import ctpop, zext
from hwtHls.frontend.pyBytecode import hlsBytecode


class AddTreeHwModule(_BaseALU1HwModule):
    """
    common adder implementations:
        https://www.elprocus.com/carry-save-adder/
        Carry Look-Ahead Adder (CLA):
            The Carry Look-Ahead Adder is designed to minimize the carry propagation delay by generating the carry signals for each bit position in advance.
            It uses a set of logic equations to compute the carry signals independently of the inputs.
            CLAs are highly parallel and can process multiple bits simultaneously, leading to faster addition operations.
            The main drawback is that CLAs require more complex hardware compared to ripple-carry or carry-select adders.
        Carry Select Adder (CSA):
            The Carry Select Adder optimizes carry propagation by using multiple sets of adders with different carry-in values and selecting the appropriate result based on the carry signal.
            CSA performs parallel additions for both carry and no-carry cases, which can speed up the addition process.
            However, CSA involves additional multiplexers and logic, which increases hardware complexity.
        Carry Save Adder (CSA):
            The Carry Save Adder is often used in applications where the sum of multiple numbers needs to be computed.
            It stores partial results and carries them separately and then performs final addition.
            While it’s efficient for certain multi-operand addition tasks, it’s not typically used for simple two-input addition operations.
    
    :ivar DATA_WIDTH_IN: the data width of inputs
    :ivar DATA_WIDTH_OUT: data width of the accumulator and the final output 
    """

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ: int = HwParam(int(20e6))
        self.UNROLL_FACTOR = HwParam(1)
        self.MAIN_FN_META = HwParam(None)
        self.CHECK_FOR_INEFFICIENCY: bool = HwParam(True)
        self.IN_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructVld)
        self.OUT_CHANNEL_TYPE: Type[HwIOStructVld] = HwParam(HwIOStructRdVld)

        self.INPUT_CNT = HwParam(4)
        self.DATA_WIDTH_IN = HwParam(16)
        self.DATA_WIDTH_OUT = HwParam(16)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        assert self.DATA_WIDTH_IN <= self.DATA_WIDTH_OUT
        self._addDataInDataOut(HBits(self.DATA_WIDTH_IN)[self.INPUT_CNT],
                               HBits(self.DATA_WIDTH_OUT))

    @override
    def _shouldInlineAluFn(self) -> bool:
        return False
    
    # def full_adder(a, b, cin):
    #    """Single full adder: returns sum, carry."""
    #    sum_bit = a ^ b ^ cin
    #    carry = (a & b) | (a & cin) | (b & cin)
    #    return sum_bit, carry
    @hwt_expr_producer
    def bitsListToBits(self, inBits: list[Union[AnyHBitsValue, int]]):
        return Concat(*(
            BIT.from_py(v) if isinstance(v, int) else v 
            for v in reversed(inBits[:self.DATA_WIDTH_OUT])
        ))

    @hlsBytecode
    @hwt_expr_producer
    def aluFn(self, inp) -> RtlSignal:
        # split input values to bits (lower bit first)
        inBits: list[list[AnyHBitsValue]] = [list(iter(dIn)) for dIn in inp]
        if self.DATA_WIDTH_IN < self.DATA_WIDTH_OUT:
            # pad to DATA_WIDTH_OUT
            padWidth = self.DATA_WIDTH_OUT - self.DATA_WIDTH_IN
            for bits in inBits:
                bits.extend(0 for _ in range(padWidth))
        
        res = HBits(self.DATA_WIDTH_OUT).from_py(None)
        while True:
            if len(inBits) == 2:
                a = zext(self.bitsListToBits(inBits[0]), self.DATA_WIDTH_OUT)
                b = zext(self.bitsListToBits(inBits[1]), self.DATA_WIDTH_OUT)
                res = a + b
                break
            elif len(inBits) == 1:
                res = zext(self.bitsListToBits(inBits[0]), self.DATA_WIDTH_OUT)
                break
            else:
                inBits = self.compressor_nToM(inBits, self.DATA_WIDTH_OUT)
        return res

    @staticmethod
    @hwt_expr_producer
    def compressor_nToM(inputs: list[list[Union[AnyHBitsValue, int]]], bitwidth: int):
        """
        This methods implements a Carry-save adder which practically is:
        * For each bit compute sum of bits on this index from all input values
        * This sum will be the output and would be shifted so the lsb is on
          the index for which this sum was computed
        
        :param inputs: numbers to sum
        :param width: the bitwidth of the number
        :note: sum is always 1 b per block
        :note: carry may have multiple bits per block, the width is computed that bits of carry and sum can store the number len(inputs) - 1
               for 3:2 compressor 1b log2ceil(3)-1, 4:2 compressor 2b, 5:2 compressor 3b
        :note: carry in width equals carry out width
        
        https://people-ece.vse.gmu.edu/coursewebpages/ECE/ECE645/S14/viewgraphs/ECE645_lecture6_multiadd.pdf
        https://www.ece.ucdavis.edu/~bbaas/281/notes/Handout.add.mult-input.pdf
        
        :note: this circuit is known under multiple mames
        "Carry-save adder (CSA)" == "(3; 2)-counter" == "3-to-2 reduction circuit" == "3:2 compressor"
        "5:3 compressor" == "5-to-3 Parallel Counter"
          
        .. code-block::text
             0101
            +0111
            +0101
            ------
               11
               1 
             11
             0 

        The max sum value is input_cnt because of that, some partial sums are known to never overlap.
        .. code-block::text
            ------
               11
               1 
             11
             0 
            ------
             1111
            +001 
    
        Thus the number of inputs for final addition is reduced. 
    
        Compressors:
        3:2
          https://github.com/Satjpatel/Verilog-HDL-Useful-Codes/blob/master/3%3A2compressor.v
        4:2
          https://github.com/Satjpatel/Verilog-HDL-Useful-Codes/blob/master/4to2compressor.v
          https://github.com/Anurag-Sharmaa/Verilog_Compressors/blob/main/Conventional_4%3A2_compressor.v
        5:2
          https://ijirt.org/publishedpaper/IJIRT154363_PAPER.pdf
          https://userpages.cs.umbc.edu/phatak/645/supl/5:2compressor.pdf
          https://www.researchgate.net/publication/355903858_Design_and_analysis_of_energy-efficient_compressors_based_on_low-power_XOR_gates_in_carbon_nanotube_technology
        """
        # sum bits in comllumns
        columnSums: list[Union[int, AnyHBitsValue]] = []
        sumBitwidth = log2ceil(len(inputs) + 1)
        for bitI in range(bitwidth):
            columnBits = []
            for inValue in inputs:
                if bitI >= len(inValue):
                    # this may happen on top bits which were truncated because they overflow to bits after bitwidth-th bit
                    pass
                else: 
                    bit = inValue[bitI]
                    if isinstance(bit, int):
                        assert bit == 0, bit
                        # does not contribute to output
                    else:
                        columnBits.append(bit)
                    
            if columnBits:
                columnSum = ctpop(Concat(*columnBits))
                assert columnSum._dtype.bit_length() <= sumBitwidth
                columnSums.append(list(iter(columnSum)))  # convert columnSum to bit list and append it to  columnSums
            else:
                # this column did not produce any value to add into output
                columnSums.append([])
        
        # merge non-overlapping sums to reduce overall number of terms
        # :note: the output will have sumBitwidth items
        outputs: list[list[Union[int, AnyHBitsValue]]] = []
        for i in range(sumBitwidth):
            # :note: the columnI occupies the columnI to columnI+len(sumBitwidth) bits
            out: list[Union[int, AnyHBitsValue]] = [0 for _ in range(i)]
            for elmI in range(ceil(bitwidth / sumBitwidth)):
                bitI = i + elmI * sumBitwidth
                if len(columnSums) <= bitI:
                    break

                columnSumBits = columnSums[bitI]
                assert len(columnSumBits) <= sumBitwidth
                padWidth = sumBitwidth - len(columnSumBits)
                # :note: by appending to out the v will receive correct offset
                out.extend(columnSumBits)
                if padWidth:
                    out.extend(0 for _ in range(padWidth))
                
                if len(out) >= bitwidth:
                    out = out[:bitwidth]
                    break
                
            outputs.append(out)
        
        assert len(outputs) < len(inputs), (len(outputs), len(inputs))
        return outputs
        
        # n = len(inputs)
        # assert n > 1
        # outputRows = log2ceil(n + 1)
        # # Initialize output rows, outputs[0] is partial sum, the remaining are carry of various degree
        # outputs = [0] * outputRows
        # # :note: column stores the binary encoded number of 1 for a given inputs at specified bit index
        # 
        # # For each bit position, compute population count and distribute across rows
        # for bit in range(bitwidth):
        #     # Count how many inputs have '1' at this bit
        #     column_count = sum((x >> bit) & 1 for x in inputs)
        # 
        #     # Encode column_count into outputCount rows:
        #     # row k gets bit k of column_count at column position 'bit'.
        #     # This is a "pure counter": each column is treated independently.
        #     for row in range(outputRows):
        #         if (column_count >> row) & 1:
        #             outputs[row] |= (1 << bit)
        # 
        # return outputs

# # 3:2 compressor example: full adder behavior
# inputs = [1, 1, 1]  # bits 1+1+1 = 3
# s, c = compressor_nToM_py(inputs, bitwidth=1, outputCount=2)
# print("3:2 compressor, inputs=1,1,1 -> sum rows:", s, c)  # should represent 3
# 
# # 5:3 compressor example at one bit position
# inputs = [1, 1, 1, 1, 1]  # 5 ones
# out = compressor_nToM_py(inputs, bitwidth=1, outputCount=3)
# print("5:3 counter, inputs=1x5 -> rows:", out)  # should encode 5 = 0b101
# 
# # Multi-bit example: compress four 4-bit numbers to two rows (like CSA tree)
# inputs = [3, 5, 7, 9]  # arbitrary
# rows = compressor_nToM_py(inputs, bitwidth=4, outputCount=3)
# print("rows:", rows, "sum of inputs:", sum(inputs))
# # Sum of rows (interpreted as plain integers) equals sum of inputs
# print("sum(rows):", sum(rows))
# 
# # 5-to-3 Parallel Counter example (multi-bit)
# print("\n=== 5-to-3 Parallel Counter Example ===")
# inputs_5to3 = [0b1011, 0b1100, 0b0111, 0b1001, 0b0101]  # 5 numbers: 11,12,7,9,5
# print("Inputs (binary):", [format(x, '04b') for x in inputs_5to3])
# print("Inputs (decimal):", inputs_5to3)
# print("Total sum:", sum(inputs_5to3))
# 
# rows_5to3 = compressor_nToM_py(inputs_5to3, bitwidth=4, outputCount=3)
# print("5-to-3 outputs (rows):")
# for i, row in enumerate(rows_5to3):
#     print(f"  Row {i}: {format(row, '04b')} = {row} (decimal)")
# 
# print("Sum of output rows:", sum(rows_5to3))
# print("✓ Matches total sum (as expected for lossless compression)")
# 
# # Verify bit-by-bit population counts
# print("\nBit position verification:")
# for bit in range(4):
#     count = sum((x >> bit) & 1 for x in inputs_5to3)
#     binary_count = format(count, '03b')
#     extracted = [(rows_5to3[row] >> bit) & 1 for row in range(3)]
#     print(f"  Bit {bit}: {count} ones → {binary_count} → extracted: {extracted}")
# 


def _OP_ADD_TREE_DoesNotUseLLVMOperator(*args):
    raise NotImplementedError("This is intended for use only in HlsNetlist")


# inputs: dataIn*, outputs: sum
# * output bitwidth may be higher than dataIn member width
OP_ADD_TREE = HOperatorDef(_OP_ADD_TREE_DoesNotUseLLVMOperator, idStr="OP_ADD_TREE")


def _OP_ADD_TREE_FRAGMENT_DoesNotUseLLVMOperator(*args):
    raise NotImplementedError()

# inputs: dataIn*, outputs: partialSum*
# OP_ADD_TREE_FRAGMENT = HOperatorDef(_OP_ADD_TREE_FRAGMENT_DoesNotUseLLVMOperator, idStr="OP_ADD_TREE_FRAGMENT")  # OP_ADD_MASKED sliced on layers to fit into clock cycle


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Medium

    m = AddTreeHwModule()
    m.ITEMS = 2
    m.CLK_FREQ = int(100e6)
    m.INPUT_CNT = 4
    m.DATA_WIDTH_IN = 8
    m.DATA_WIDTH_OUT = 8

    print(to_rtl_str(m, target_platform=Artix7Medium(
        # debugFilter={HlsDebugBundle.DBG_4_4_arch,},
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[
            # LLVM_CLI_COMMON_OPTS.debugOnly("legalizer"),
            # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
            # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
            # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
            # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
            # LLVM_CLI_COMMON_OPTS.OVERWIRTE_BB_NAMES,
            # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            ]
        )))  #

