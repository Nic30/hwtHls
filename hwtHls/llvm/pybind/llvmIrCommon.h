#pragma once

#include <llvm/Support/raw_os_ostream.h>

namespace hwtHls {

template<typename T>
std::string printToStr(T *self) {
	std::string tmp;
	llvm::raw_string_ostream ss(tmp);
	self->print(ss);
	return ss.str();
}

}
