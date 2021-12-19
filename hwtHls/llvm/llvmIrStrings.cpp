#include "llvmIrStrings.h"

#include "llvm/ADT/StringRef.h"
#include "llvm/ADT/Twine.h"

namespace py = pybind11;

std::string StringRef__repr__(llvm::StringRef *self) {
	return std::string("<StringRef ") + self->str() + ">";
}

std::string Twine__repr__(llvm::Twine *self) {
	return std::string("<Twine ") + self->str() + ">";
}

class LLVMStringContext {
	std::vector<std::string> _all_strings;
public:
	LLVMStringContext() {
	}
	llvm::StringRef addStringRef(const std::string &str) {
		// copy string to cache to make it persistent in C/C++
		_all_strings.push_back(str);
		return llvm::StringRef(_all_strings.back());
	}
	llvm::Twine addTwine(const std::string &str) {
		_all_strings.push_back(str);
		return llvm::Twine(_all_strings.back());
	}
};

void register_strings(pybind11::module_ & m) {
	py::class_<llvm::StringRef>(m, "StringRef")
		.def("__repr__", &StringRef__repr__)
		.def("str", & llvm::StringRef::str);
	py::class_<llvm::Twine>(m, "Twine")
		.def("__repr__", &Twine__repr__)
		.def("str", & llvm::Twine::str);
	py::class_<LLVMStringContext>(m, "LLVMStringContext")
		.def(py::init<>())
		.def("addStringRef", &LLVMStringContext::addStringRef, py::return_value_policy::reference)
		.def("addTwine", &LLVMStringContext::addTwine, py::return_value_policy::reference);
}
