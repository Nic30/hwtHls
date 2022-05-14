#pragma once

#include <pybind11/pybind11.h>
#include <llvm/ADT/StringRef.h>
#include <llvm/ADT/Twine.h>

class LLVMStringContext {
protected:
	std::vector<std::string> _all_strings;
public:
	LLVMStringContext();
	llvm::StringRef addStringRef(const std::string &str);
	llvm::Twine addTwine(const std::string &str);
};

void register_strings(pybind11::module_ &m);

