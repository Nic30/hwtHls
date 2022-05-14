#include "llvmIrValues.h"
#include "llvmIrCommon.h"


#include <llvm/ADT/APInt.h>
#include <llvm/ADT/APSInt.h>
#include <llvm/ADT/SmallString.h>
#include <llvm/IR/Constants.h>

namespace py = pybind11;


namespace pybind11 __attribute__((visibility("hidden"))) {
	class int_fromStr : public py::int_ {
	public:
		int_fromStr(const std::string & str) {
			m_ptr = PyLong_FromString(str.c_str(), nullptr, 16);
		}
	};
}


void register_Values_and_Use(pybind11::module_ & m) {
	py::class_<llvm::Value, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
			.def("__repr__", &printToStr<llvm::Value>)
			.def("__hash__", [](llvm::Value * v) {
				return reinterpret_cast<intptr_t>(v);
			})
			.def("__eq__", [](llvm::Value * v0, llvm::Value * v1){
				return v0 == v1;
			})
			.def("getType", &llvm::Value::getType, py::return_value_policy::reference)
			.def("getName", &llvm::Value::getName)
			.def("users", [](llvm::Value &v) {
				auto users = v.users();
			 	return py::make_iterator(users.begin(), users.end());
			 }, py::keep_alive<0, 1>());

	// owned by context => no delete
	py::class_<llvm::User, std::unique_ptr<llvm::User, py::nodelete>, llvm::Value>(m, "User")
		.def("iterOperands", [](llvm::User &v) {
			 	return py::make_iterator(v.op_begin(), v.op_end());
			 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */;

	py::class_<llvm::Use, std::unique_ptr<llvm::Use, py::nodelete>>(m, "Use")
		.def("get", &llvm::Use::get);

	py::class_<llvm::APInt>(m, "APInt")
		.def(py::init<unsigned, llvm::StringRef, uint8_t>())
		.def_static("getAllOnesValue", llvm::APInt::getAllOnesValue)
		.def_static("getBitsSet", llvm::APInt::getBitsSet)
		.def("__int__", [](llvm::APInt* I) {
		 	 llvm::SmallString<256> str;
			I->toString(str, 16, I->isNegative());
			return pybind11::int_fromStr(str.c_str());
		});

	py::class_<llvm::Constant, std::unique_ptr<llvm::Constant, py::nodelete>, llvm::User>(m, "Constant");
	py::class_<llvm::ConstantData, std::unique_ptr<llvm::ConstantData, py::nodelete>, llvm::Constant>(m, "ConstantData");
	py::class_<llvm::ConstantInt, std::unique_ptr<llvm::ConstantInt, py::nodelete>, llvm::ConstantData>(m, "ConstantInt")
		.def_static("get", [](llvm::Type* Ty, llvm::APInt& V) {
			return llvm::ConstantInt::get(Ty, V);
		}, py::return_value_policy::reference)
		.def("getValue", &llvm::ConstantInt::getValue);
	m.def("ValueToConstantInt", [](llvm::Value * V) {
		  if (llvm::ConstantInt *CI = llvm::dyn_cast<llvm::ConstantInt>(V)) {
		    return CI;
		  } else {
			  return (llvm::ConstantInt *) nullptr;
		  }
	});

}
