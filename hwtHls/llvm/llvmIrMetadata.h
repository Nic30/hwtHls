#include <pybind11/pybind11.h>

#include <llvm/IR/Metadata.h>

namespace hwtHls {

// the object itself is always managed by LLVMContext
// there is a bug in pybind11 https://github.com/pybind/pybind11/issues/2068 which prevents using protected delete operator
class MDNodeWithDeletedDelete: public llvm::MDNode {
public:
	void operator delete(void *Mem) = delete;
	void operator delete(void*, unsigned) = delete;
	void operator delete(void*, unsigned, bool) = delete;
};

class MDTupleWithDeletedDelete: public MDNodeWithDeletedDelete,
		public llvm::MDTuple {
public:
	void operator delete(void *Mem) = delete;
	void operator delete(void*, unsigned) = delete;
	void operator delete(void*, unsigned, bool) = delete;
};

void register_Attribute(pybind11::module_ &m);
void register_MDNode(pybind11::module_ &m);
}
