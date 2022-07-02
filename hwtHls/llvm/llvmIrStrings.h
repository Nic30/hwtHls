#pragma once

#include <pybind11/pybind11.h>
#include <llvm/ADT/StringRef.h>
#include <llvm/ADT/Twine.h>
#include <list>

namespace hwtHls {

class LLVMStringContext {
protected:
	// :attention: we can not use container which reallocates (std:vector, map, ...) because we are taking address od string data
	std::list<std::string> _all_strings;
public:
	LLVMStringContext();
	llvm::StringRef addStringRef(const std::string &str);
	llvm::Twine addTwine(const std::string &str);
};

void register_strings(pybind11::module_ &m);

}
