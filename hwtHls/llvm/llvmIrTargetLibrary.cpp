#include <hwtHls/llvm/llvmIrTargetLibrary.h>
#include <hwtHls/llvm/llvmCompilationBundle.h>

#include <llvm/Analysis/TargetLibraryInfo.h>

namespace py = pybind11;

namespace hwtHls {

void register_TargetLibrary(pybind11::module_ &m) {
	py::class_<llvm::TargetLibraryInfo,
			std::unique_ptr<llvm::TargetLibraryInfo, py::nodelete>> TargetLibraryInfo(
			m, "TargetLibraryInfo");

	py::enum_<llvm::LibFunc> LibFunc(m, "LibFunc");

	llvm::TargetLibraryInfoImpl TLII(
			llvm::Triple(LlvmCompilationBundle::TargetTriple));
	for (unsigned _fnId = 0; _fnId < llvm::LibFunc::NumLibFuncs; _fnId++) {
		auto fnId = llvm::LibFunc(_fnId);
		// must make available or name is ""
		// :note: must be done in advance because TargetLibraryInfo makes copy
		TLII.setAvailable(fnId);
	}
	llvm::TargetLibraryInfo TLI(TLII);
	for (unsigned _fnId = 0; _fnId < llvm::LibFunc::NumLibFuncs; _fnId++) {
		auto fnId = llvm::LibFunc(_fnId);
		auto name = TLI.getName(fnId).str();
		bool nameIsId = find_if(name.begin(), name.end(), [](char c) {
			return !(isalnum(c) || c == '_');
		}) == name.end();
		if (!nameIsId || name.empty()) {
			// some strings of library function do not correspond to its name in enum
			// without parsing TargetLibraryInfo.def we can not resolve them
			continue;
		}
		if (name.starts_with("__")) {
			name = name.substr(2, name.length() - 2);
			switch (fnId) {
			case llvm::LibFunc::LibFunc_dunder_strdup:
			case llvm::LibFunc::LibFunc_dunder_strndup:
			case llvm::LibFunc::LibFunc_dunder_strtok_r:
			case llvm::LibFunc::LibFunc_dunder_isoc99_scanf:
			case llvm::LibFunc::LibFunc_dunder_isoc99_sscanf:
				name = "dunder_" + name;
				break;
			default:
				break;
			}
		} else if (name.starts_with("_")) {
			name = name.substr(1, name.length() - 1);
			switch (fnId) {
			case llvm::LibFunc::LibFunc_under_IO_getc:
			case llvm::LibFunc::LibFunc_under_IO_putc:
				name = "under_" + name;
				break;
			default:
				break;
			}
		}
		name = "LibFunc_" + name;
		LibFunc.value(name.c_str(), fnId);
	}
	LibFunc.value("NumLibFuncs", llvm::LibFunc::NumLibFuncs);
	LibFunc.value("NotLibFunc", llvm::LibFunc::NotLibFunc);
}

}
