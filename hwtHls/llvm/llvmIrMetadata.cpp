#include <hwtHls/llvm/llvmIrMetadata.h>

#include <pybind11/stl.h>
#include <hwtHls/llvm/llvmIrCommon.h>

namespace py = pybind11;

namespace hwtHls {

void register_Attribute(pybind11::module_ & m) {
	//llvm::AttributeSet
	//py::class_<llvm::Attribute, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
}

template<typename T>
llvm::Metadata * asMetadata(T * x) {
	return reinterpret_cast<llvm::Metadata*>(x);
}

void register_MDNode(pybind11::module_ & m) {
	py::class_<llvm::Metadata, std::unique_ptr<llvm::Metadata, py::nodelete>> Metadata(m, "Metadata");
	Metadata
		.def("asMetadata", &asMetadata<llvm::Metadata>, py::return_value_policy::reference_internal)
		.def("__repr__", &printToStr<llvm::Metadata>);

	py::class_<MDNodeWithDeletedDelete, std::unique_ptr<MDNodeWithDeletedDelete, py::nodelete>> MDNode(m, "MDNode");
	MDNode
		.def_static("get", [](llvm::LLVMContext &Context, std::vector<llvm::Metadata *> &MDs, bool insertTmpAsFirts) {
				llvm::MDTuple * res = llvm::MDNode::get(Context, MDs);
				if (insertTmpAsFirts) {
					std::vector<llvm::Metadata *> MDs_tmp;
					// llvm::MDNode::getTemporary(Context, {}).get()
					MDs_tmp.push_back(nullptr);
					MDs_tmp.insert(MDs_tmp.end(), MDs.begin(), MDs.end());
					res  = llvm::MDNode::get(Context, MDs_tmp);
					res->replaceOperandWith(0, res);
				} else {
					res = llvm::MDNode::get(Context, MDs);
				}
				return reinterpret_cast<MDTupleWithDeletedDelete*>(res);
			}, py::return_value_policy::reference,  py::keep_alive<0, 2>(), py::arg("Context"), py::arg("MDs"), py::arg("insertTmpAsFirts") = false)
		.def_static("getTemporary", [](llvm::LLVMContext &Context, const std::vector<llvm::Metadata *> &MDs) {
				auto res = llvm::MDNode::getTemporary(Context, MDs);
				return res;
			}, py::return_value_policy::reference_internal)
		.def_static("getDistinct", [](llvm::LLVMContext &Context, const std::vector<llvm::Metadata *> &MDs) {
			auto * res = llvm::MDNode::getDistinct(Context, MDs);
			return reinterpret_cast<MDTupleWithDeletedDelete*>(res);
		}, py::return_value_policy::reference_internal)
		.def("replaceOperandWith", [](MDNodeWithDeletedDelete* self, unsigned I, llvm::Metadata *New) {
			reinterpret_cast<llvm::MDNode*>(self)->replaceOperandWith(I, New);
		},  py::keep_alive<0, 2>())
		.def("asMetadata", &asMetadata<MDNodeWithDeletedDelete>, py::return_value_policy::reference_internal)
		.def("getOperand", &MDNodeWithDeletedDelete::getOperand, py::return_value_policy::reference_internal)
		.def("getNumOperands", &MDNodeWithDeletedDelete::getNumOperands)
		.def("iterOperands", [](MDNodeWithDeletedDelete &v) {
			 	return py::make_iterator(v.op_begin(), v.op_end());
			 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("__eq__", [](MDNodeWithDeletedDelete* self, MDNodeWithDeletedDelete* other) {
			return self == other;
		})
		.def("__eq__", [](MDNodeWithDeletedDelete* self, llvm::Metadata* other) {
			return self == other;
		})
		.def("__repr__", &printToStr<MDNodeWithDeletedDelete>);
	m.def("MetadataAsMDNode", [](llvm::Metadata * MD) {
		return dyn_cast<MDNodeWithDeletedDelete>(MD);
	}, py::return_value_policy::reference_internal);

	py::class_<llvm::MDOperand, std::unique_ptr<llvm::MDOperand>> MDOperand(m, "MDOperand");
	MDOperand.def("get", &llvm::MDOperand::get);

	py::class_<MDTupleWithDeletedDelete, std::unique_ptr<MDTupleWithDeletedDelete, py::nodelete>,
		MDNodeWithDeletedDelete> MDTuple(m, "MDTuple");
	MDTuple
		.def("asMetadata", &asMetadata<MDTupleWithDeletedDelete>, py::return_value_policy::reference_internal)
		.def("__repr__", [](MDTupleWithDeletedDelete * self) {
			std::string tmp;
			llvm::raw_string_ostream ss(tmp);
			reinterpret_cast<llvm::MDTuple*>(self)->print(ss);
			return ss.str();
		});

	// "metadata literals"
	py::class_<llvm::ValueAsMetadata, std::unique_ptr<llvm::ValueAsMetadata, py::nodelete>,
		llvm::Metadata> ValueAsMetadata(m, "ValueAsMetadata");
	ValueAsMetadata
		.def_static("get", llvm::ValueAsMetadata::get, py::return_value_policy::reference_internal)
		.def("getValue", &llvm::ValueAsMetadata::getValue, py::return_value_policy::reference_internal)
		.def("__repr__", &printToStr<llvm::ValueAsMetadata>);
	m.def("MetadataAsValueAsMetadata", [](llvm::Metadata * MD) {
		return dyn_cast<llvm::ValueAsMetadata>(MD);
	}, py::return_value_policy::reference_internal);

	py::class_<llvm::ConstantAsMetadata, std::unique_ptr<llvm::ConstantAsMetadata, py::nodelete>,
		llvm::ValueAsMetadata> ConstantAsMetadata(m, "ConstantAsMetadata");
	ConstantAsMetadata
		.def("asMetadata", &asMetadata<llvm::ConstantAsMetadata>, py::return_value_policy::reference_internal)
		.def("__repr__", &printToStr<llvm::ConstantAsMetadata>);

	ValueAsMetadata
		.def("asMetadata", &asMetadata<llvm::ValueAsMetadata>, py::return_value_policy::reference_internal)
		.def_static("getConstant", &llvm::ValueAsMetadata::getConstant, py::return_value_policy::reference_internal);

	py::class_<llvm::MDString, std::unique_ptr<llvm::MDString, py::nodelete>, llvm::Metadata>(m, "MDString")
		.def_static("get", [](llvm::LLVMContext &Context, llvm::StringRef Str) {
			return llvm::MDString::get(Context, Str);
		}, py::return_value_policy::reference_internal)
		.def("asMetadata", &asMetadata<llvm::MDString>, py::return_value_policy::reference_internal)
		.def("__repr__", &printToStr<llvm::MDString>);

	py::implicitly_convertible<MDTupleWithDeletedDelete, MDNodeWithDeletedDelete>();
	py::implicitly_convertible<MDNodeWithDeletedDelete, llvm::Metadata>();
	py::implicitly_convertible<llvm::MDString, llvm::Metadata>();
	//py::implicitly_convertible<MDNodeWithDeletedDelete, llvm::Metadata>();
	//py::implicitly_convertible<llvm::ConstantAsMetadata, llvm::Metadata>();
	//py::implicitly_convertible<llvm::ValueAsMetadata, llvm::Metadata>();
	//py::implicitly_convertible<llvm::MDString, llvm::Metadata>();
}

}
