#include <hwtHls/llvm/llvmIrValues.h>

#include <sstream>

#include <pybind11/stl.h>
#include <hwtHls/llvm/llvmIrCommon.h>

#include <llvm/ADT/APInt.h>
#include <llvm/ADT/APFloat.h>
#include <llvm/ADT/APSInt.h>
#include <llvm/ADT/SmallString.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/GlobalValue.h>


namespace py = pybind11;


namespace pybind11 __attribute__((visibility("hidden"))) {
	class int_fromStr : public py::int_ {
	public:
		int_fromStr(const std::string & str) {
			m_ptr = PyLong_FromString(str.c_str(), nullptr, 16);
		}
	};
}

namespace hwtHls {

template<typename T>
T* llvmValueCaster(llvm::Value *V) {
	if (T *_V = llvm::dyn_cast<T>(V)) {
		return _V;
	} else {
		return (T*) nullptr;
	}
}

class ConstantElementIterator {
	llvm::Constant& C;
	size_t currentIndex;
public:
	ConstantElementIterator(llvm::Constant &C, size_t currentIndex) :
			C(C), currentIndex(currentIndex) {
	}

    llvm::Constant & operator*() const {
    	return *C.getAggregateElement(currentIndex);
    }
    llvm::Constant * operator->() const {
    	return C.getAggregateElement(currentIndex);
    }

    ConstantElementIterator& operator++() {
    	currentIndex++;
    	return *this;
    }
    ConstantElementIterator operator++(int) {
    	currentIndex++;
    	return *this;
    }

    friend bool operator==(ConstantElementIterator a, ConstantElementIterator b) {
    	assert(&a.C == &b.C);
    	return a.currentIndex == b.currentIndex;
    }
    friend bool operator!=(ConstantElementIterator a, ConstantElementIterator b){
    	assert(&a.C == &b.C);
    	return a.currentIndex != b.currentIndex;
    }
};

void register_Values_and_Use(pybind11::module_ & m) {
	py::class_<llvm::Value, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
			.def("__repr__", &printToStr<llvm::Value>)
			.def("__str__", &printToStr<llvm::Value>)
			.def("__hash__", [](llvm::Value * v) {
				return reinterpret_cast<intptr_t>(v);
			})
			.def("__eq__", [](llvm::Value * v0, llvm::Value * v1){
				return v0 == v1;
			})
			.def("getType", &llvm::Value::getType, py::return_value_policy::reference)
			.def("getName", &llvm::Value::getName)
			.def("getNumUses", &llvm::Value::getNumUses)
			.def("hasOneUse", &llvm::Value::hasOneUse)
			.def("hasOneUser", &llvm::Value::hasOneUser)
			.def("users", [](llvm::Value &v) {
				auto users = v.users();
			 	return py::make_iterator(users.begin(), users.end());
			 }, py::keep_alive<0, 1>());

	// owned by context => no delete
	py::class_<llvm::User, std::unique_ptr<llvm::User, py::nodelete>, llvm::Value>(m, "User")
		.def("getOperand", &llvm::User::getOperand, py::return_value_policy::reference)
		.def("getNumOperands", &llvm::User::getNumOperands)
		.def("iterOperands", [](llvm::User &v) {
			 	return py::make_iterator(v.op_begin(), v.op_end());
			 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("iterOperandValues", [](llvm::User &v) {
		 	return py::make_iterator(v.value_op_begin(), v.value_op_end());
		 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	py::class_<llvm::Use, std::unique_ptr<llvm::Use, py::nodelete>>(m, "Use")
		.def("get", &llvm::Use::get, py::return_value_policy::reference);

	py::class_<llvm::APInt>(m, "APInt")
		.def(py::init<unsigned, llvm::StringRef, uint8_t>())
		.def_static("getAllOnes", llvm::APInt::getAllOnes)
		.def_static("getBitsSet", llvm::APInt::getBitsSet)
		.def("getZExtValue", &llvm::APInt::getZExtValue)
		.def("__int__", [](llvm::APInt* I) {
		 	llvm::SmallString<256> str;
			I->toString(str, 16, I->isNegative());
			return pybind11::int_fromStr(str.c_str());
		});
	py::class_<llvm::APFloat>(m, "APFloat")
		.def(py::init<double>())
		.def("__float__", [](llvm::APFloat* self) {
			return self->convertToDouble();
		})
		.def("__str__", [](llvm::APFloat* self) {
			std::stringstream sb("<APFloat ");
			sb << self->convertToDouble();
			sb << ">";
			return sb.str();
		});

	py::class_<llvm::Constant, std::unique_ptr<llvm::Constant, py::nodelete>, llvm::User> Constant(m, "Constant");
	Constant
	.def("__iter__", [](llvm::Constant &self) {
		size_t numElements;
		if (auto ArrTy = dyn_cast<llvm::ArrayType>(self.getType())) {
			numElements = ArrTy->getNumElements();
		}
		return py::make_iterator(ConstantElementIterator(self, 0), ConstantElementIterator(self, numElements));
	}, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
	.def("getAggregateElement",
			[](llvm::Constant &self, unsigned index) {
				return self.getAggregateElement(index);
			}, py::return_value_policy::reference);
	py::class_<llvm::GlobalValue, std::unique_ptr<llvm::GlobalValue, py::nodelete>, llvm::Constant> GlobalValue(m, "GlobalValue");
	py::enum_<llvm::GlobalValue::LinkageTypes>(GlobalValue, "LinkageTypes")
    	 .value("ExternalLinkage",           llvm::GlobalValue::LinkageTypes::ExternalLinkage,           "Externally visible function")
    	 .value("AvailableExternallyLinkage",llvm::GlobalValue::LinkageTypes::AvailableExternallyLinkage,"Available for inspection, not emission.")
    	 .value("LinkOnceAnyLinkage",        llvm::GlobalValue::LinkageTypes::LinkOnceAnyLinkage,        "Keep one copy of function when linking (inline)")
    	 .value("LinkOnceODRLinkage",        llvm::GlobalValue::LinkageTypes::LinkOnceODRLinkage,        "Same, but only replaced by something equivalent.")
    	 .value("WeakAnyLinkage",            llvm::GlobalValue::LinkageTypes::WeakAnyLinkage,            "Keep one copy of named function when linking (weak)")
    	 .value("WeakODRLinkage",            llvm::GlobalValue::LinkageTypes::WeakODRLinkage,            "Same, but only replaced by something equivalent.")
    	 .value("AppendingLinkage",          llvm::GlobalValue::LinkageTypes::AppendingLinkage,          "Special purpose, only applies to global arrays")
    	 .value("InternalLinkage",           llvm::GlobalValue::LinkageTypes::InternalLinkage,           "Rename collisions when linking (static functions).")
    	 .value("PrivateLinkage",            llvm::GlobalValue::LinkageTypes::PrivateLinkage,            "Like Internal, but omit from symbol table.")
    	 .value("ExternalWeakLinkage",       llvm::GlobalValue::LinkageTypes::ExternalWeakLinkage,       "ExternalWeak linkage description.")
    	 .value("CommonLinkage",             llvm::GlobalValue::LinkageTypes::CommonLinkage,             "Tentative definitions.")
    	 .export_values();
	py::enum_<llvm::GlobalValue::UnnamedAddr>(GlobalValue, "UnnamedAddr")
		.value("None",   llvm::GlobalValue::UnnamedAddr::None)
		.value("Local",  llvm::GlobalValue::UnnamedAddr::Local)
		.value("Global", llvm::GlobalValue::UnnamedAddr::Global)
		.export_values();
	py::class_<llvm::ConstantData, std::unique_ptr<llvm::ConstantData, py::nodelete>, llvm::Constant>(m, "ConstantData");
	py::class_<llvm::ConstantAggregate,  std::unique_ptr<llvm::ConstantAggregate, py::nodelete>, llvm::Constant>(m, "ConstantAggregate");
	py::class_<llvm::ConstantDataSequential,  std::unique_ptr<llvm::ConstantDataSequential, py::nodelete>, llvm::ConstantData>(m, "ConstantDataSequential");

	py::class_<llvm::ConstantInt, std::unique_ptr<llvm::ConstantInt, py::nodelete>, llvm::ConstantData>(m, "ConstantInt")
		.def_static("get", [](llvm::Type* Ty, llvm::APInt& V) {
			return llvm::ConstantInt::get(Ty, V);
		}, py::return_value_policy::reference)
		.def("getValue", &llvm::ConstantInt::getValue);
	m.def("ValueToConstantInt", &llvmValueCaster<llvm::ConstantInt>, py::return_value_policy::reference);

	py::class_<llvm::ConstantFP, std::unique_ptr<llvm::ConstantFP, py::nodelete>, llvm::ConstantData>(m, "ConstantFP")
		.def_static("get", [](llvm::Type* Ty, llvm::APFloat& V) {
			return llvm::ConstantFP::get(Ty, V);
		}, py::return_value_policy::reference)
		.def_static("get", [](llvm::Type* Ty, double V) {
			return llvm::ConstantFP::get(Ty, V);
		}, py::return_value_policy::reference)
		.def("getValue", &llvm::ConstantFP::getValue);
	m.def("ValueToConstantFP", &llvmValueCaster<llvm::ConstantFP>, py::return_value_policy::reference);

	py::class_<llvm::ConstantArray, std::unique_ptr<llvm::ConstantArray, py::nodelete>, llvm::ConstantAggregate> ConstantArray(m, "ConstantArray");
	ConstantArray //
	.def_static("get",
			[](llvm::ArrayType *T, const std::vector<llvm::Constant*> &V) {
				return llvm::ConstantArray::get(T, V);
			});

	m.def("ValueToConstantArray", &llvmValueCaster<llvm::ConstantArray>, py::return_value_policy::reference);
	py::class_<llvm::ConstantDataArray, std::unique_ptr<llvm::ConstantDataArray, py::nodelete>, llvm::ConstantDataSequential>(m, "ConstantDataArray");
	m.def("ValueToConstantDataArray", &llvmValueCaster<llvm::ConstantDataArray>, py::return_value_policy::reference);

	py::class_<llvm::UndefValue, std::unique_ptr<llvm::UndefValue, py::nodelete>, llvm::ConstantData>(m, "UndefValue")
		.def_static("get", &llvm::UndefValue::get, py::return_value_policy::reference);
	m.def("ValueToUndefValue", &llvmValueCaster<llvm::UndefValue>, py::return_value_policy::reference);

}

}
