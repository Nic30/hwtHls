#include "llvmIrMetadata.h"
#include <pybind11/stl.h>

#include "llvmIrCommon.h"
namespace py = pybind11;

namespace hwtHls {


//namespace pybind11 {
//    template<> struct polymorphic_type_hook<MDTupleWithDeletedDelete> {
//        static const void *get(const MDTupleWithDeletedDelete *src, const std::type_info*& type) {
//            // note that src may be nullptr
//            if (src && src->kind == PetKind::Dog) {
//                type = &typeid(Dog);
//                return static_cast<const MDNodeWithDeletedDelete*>(src);
//            }
//            return src;
//        }
//    };
//}

void register_Attribute(pybind11::module_ & m) {
	//llvm::AttributeSet
	//py::class_<llvm::Attribute, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
}

void register_MDNode(pybind11::module_ & m) {
	py::class_<llvm::Metadata, std::unique_ptr<llvm::Metadata, py::nodelete>> Metadata(m, "Metadata");
	Metadata.def("__repr__", &printToStr<llvm::Metadata>);
	py::class_<MDNodeWithDeletedDelete, std::unique_ptr<MDNodeWithDeletedDelete, py::nodelete>> MDNode(m, "MDNode");
	MDNode
		.def("getDistinct", [](llvm::LLVMContext &Context, std::vector<llvm::Metadata *> &MDs) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(llvm::MDNode::getDistinct(Context, MDs));
		}, py::return_value_policy::reference)
		.def("__repr__", &printToStr<MDNodeWithDeletedDelete>)
		.def("reprMDNode", &printToStr<MDNodeWithDeletedDelete>);
	py::class_<MDTupleWithDeletedDelete, std::unique_ptr<MDTupleWithDeletedDelete, py::nodelete>, MDNodeWithDeletedDelete> MDTuple(m, "MDTuple");
	MDTuple
		.def("__repr__", [](MDTupleWithDeletedDelete * self) {
			std::string tmp;
			llvm::raw_string_ostream ss(tmp);
			static_cast<llvm::MDTuple*>(self)->print(ss);
			return ss.str();
		});

	// "metadata literals"
	py::class_<llvm::ValueAsMetadata, std::unique_ptr<llvm::ValueAsMetadata, py::nodelete>,
		llvm::Metadata> ValueAsMetadata(m, "ValueAsMetadata");
	ValueAsMetadata.def("__repr__", &printToStr<llvm::ValueAsMetadata>);
	py::class_<llvm::ConstantAsMetadata, std::unique_ptr<llvm::ConstantAsMetadata, py::nodelete>,
		llvm::ValueAsMetadata> ConstantAsMetadata(m, "ConstantAsMetadata");
	ValueAsMetadata
		.def("getConstant", &llvm::ValueAsMetadata::getConstant, py::return_value_policy::reference)
		.def("__repr__", &printToStr<llvm::ConstantAsMetadata>);
	py::class_<llvm::MDString, llvm::Metadata>(m, "MDString")
		.def("get", [](llvm::LLVMContext &Context, llvm::StringRef Str) {
			llvm::MDString::get(Context, Str);
		}, py::return_value_policy::reference);
	py::implicitly_convertible<MDTupleWithDeletedDelete, MDNodeWithDeletedDelete>();
}

}
