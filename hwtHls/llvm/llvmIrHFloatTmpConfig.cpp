#include <hwtHls/llvm/llvmIrHFloatTmpConfig.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>

#include <llvm/CodeGen/MachineInstr.h>
#include <pybind11/native_enum.h>

namespace py = pybind11;

namespace hwtHls {

void register_HFloatTmpConfig(pybind11::module_ &m) {
	py::native_enum<hwtHls::HFloatTmpRounding>(m, "HFloatTmpRounding", "enum.Enum")
		.value("ROUND_HALF_EVEN", hwtHls::HFloatTmpRounding::ROUND_HALF_EVEN)
		.value("ROUND_HALF_UP", hwtHls::HFloatTmpRounding::ROUND_HALF_UP)
		.value("ROUND_DOWN", hwtHls::HFloatTmpRounding::ROUND_DOWN)
		.value("ROUND_CEILING", hwtHls::HFloatTmpRounding::ROUND_CEILING)
		.value("ROUND_FLOOR", hwtHls::HFloatTmpRounding::ROUND_FLOOR)
		.value("ROUND_WIDTH", hwtHls::HFloatTmpRounding::ROUND_WIDTH)
		.value("ROUND_C_DEFAULT", hwtHls::HFloatTmpRounding::ROUND_C_DEFAULT)
		.finalize()
		;
	py::native_enum<hwtHls::HFloatTmpSaturation>(m, "HFloatTmpSaturation", "enum.Enum")
		.value("SATURATE_NONE", hwtHls::HFloatTmpSaturation::SATURATE_NONE)
		.value("SATURATE_INF", hwtHls::HFloatTmpSaturation::SATURATE_INF)
		.value("SATURATE_WIDTH", hwtHls::HFloatTmpSaturation::SATURATE_WIDTH)
		.value("SATURATE_C_DEFAULT", hwtHls::HFloatTmpSaturation::SATURATE_C_DEFAULT)
		.finalize()
		;
	py::class_<hwtHls::HFloatTmpConfig>(m, "HFloatTmpConfig")
		.def(py::init<bool,
				unsigned, unsigned,
				bool,
				bool, bool, bool,
				bool, bool,
				hwtHls::HFloatTmpRounding,
				hwtHls::HFloatTmpSaturation>(),
				py::arg("isInQFormat"),
				py::arg("exponentOrIntWidth"), py::arg("mantissaOrFracWidth"),
				py::arg("supportSubnormal")=true,
				py::arg("hasSign") = true, py::arg("hasIsNaN") = false, py::arg("hasIsInf") = false,
				py::arg("hasIs1")= false, py::arg("hasIs0")= false,
				py::arg("rounding")= HFloatTmpRounding::ROUND_C_DEFAULT,
				py::arg("saturation")= HFloatTmpSaturation::SATURATE_C_DEFAULT)
		.def("copy", [](hwtHls::HFloatTmpConfig & self) {
			return hwtHls::HFloatTmpConfig(self);
		})
		.def_readonly_static("MEMBER_CNT", &hwtHls::HFloatTmpConfig::MEMBER_CNT)
		.def_static("fromCallArgs", &hwtHls::HFloatTmpConfig::fromCallArgs, py::arg("call"), py::arg("argsToSkip")=1u)
		.def_static("fromMachineInstrOperands", [](llvm::MachineInstr & MI, size_t operandOffset) {
			assert(HFloatTmpConfig::MEMBER_CNT == 11);
			if (MI.getNumExplicitOperands()
					< operandOffset + HFloatTmpConfig::MEMBER_CNT + 1) {
				throw std::runtime_error(
						"Instruction does not have enough operands to extract HFloatTmpConfig, (ops should end with HFloatTmpConfig members and enCond)");
			}
			if (!MI.getOperand(operandOffset).isImm()) {
				throw std::runtime_error(
								"The first selected operand and all following for HFloatTmpConfig must be Imm");
			}
			return hwtHls::HFloatTmpConfig::fromMachineInstrOperands(MI, operandOffset);
		}, py::arg("MI"), py::arg("operandOffset"))
		.def_readwrite("isInQFormat", &HFloatTmpConfig::isInQFormat)
		.def_readwrite("exponentOrIntWidth", &HFloatTmpConfig::exponentOrIntWidth)
		.def_readwrite("mantissaOrFracWidth", &HFloatTmpConfig::mantissaOrFracWidth)
		.def_readwrite("supportSubnormal", &HFloatTmpConfig::supportSubnormal)
		.def_readwrite("hasSign", &HFloatTmpConfig::hasSign)
		.def_readwrite("hasIsNaN", &HFloatTmpConfig::hasIsNaN)
		.def_readwrite("hasIsInf", &HFloatTmpConfig::hasIsInf)
		.def_readwrite("hasIs1", &HFloatTmpConfig::hasIs1)
		.def_readwrite("hasIs0", &HFloatTmpConfig::hasIs0)
		.def_readwrite("rounding", &HFloatTmpConfig::rounding)
		.def_readwrite("saturation", &HFloatTmpConfig::saturation)
		.def("getBitWidth", &hwtHls::HFloatTmpConfig::getBitWidth)
		.def("bitCastAPFloatToHFloatTmpAPInt", &HFloatTmpConfig::bitCastAPFloatToHFloatTmpAPInt)
		.def("bitCastHFloatTmpAPIntToAPFloat", &HFloatTmpConfig::bitCastHFloatTmpAPIntToAPFloat)
		.def("__hash__", &hwtHls::HFloatTmpConfig::__hash__)
		.def("__eq__", [](hwtHls::HFloatTmpConfig * self, hwtHls::HFloatTmpConfig * other) {
			return *self == *other;
		})
		.def("__repr__", [](hwtHls::HFloatTmpConfig & self) {
			std::string errStr = "";
			llvm::raw_string_ostream ss(errStr);
			self.print(ss);
			return ss.str();
		});
}
}
