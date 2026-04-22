#include <hwtHls/llvm/llvmIrMetadata.h>

#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <hwtHls/llvm/llvmIrCommon.h>
#include <hwtHls/llvm/intrinsic/metadataThreadHwtComponent.h>
#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>
#include <hwtHls/llvm/Transforms/IoLowerAxiMMPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/ThreadExtractIoFsmPass.h>

#include <pybind11/native_enum.h>

namespace py = pybind11;

PYBIND11_MAKE_OPAQUE(std::vector<llvm::Metadata*>);

namespace hwtHls {

void register_Attribute(pybind11::module_ & m) {
	//llvm::AttributeSet
	//py::class_<llvm::Attribute, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
}

template<typename T>
llvm::Metadata * asMetadata(T * x) {
	return reinterpret_cast<llvm::Metadata*>(x);
}


void register_HwtHlsIoMetadata(pybind11::module_ & m) {
	py::native_enum<hwtHls::IODirection> (m, "IODirection", "enum.Enum")
		.value("IO_DIR_IN", hwtHls::IODirection::IO_DIR_IN)
		.value("IO_DIR_OUT", hwtHls::IODirection::IO_DIR_OUT)
		.value("IO_DIR_UNRESOLVED", hwtHls::IODirection::IO_DIR_UNRESOLVED)
		.finalize();
	py::native_enum<hwtHls::IOVectorizationType> (m, "IOVectorizationType", "enum.Enum")
		.value("IOV_SCALAR_PACKED", hwtHls::IOVectorizationType::IOV_SCALAR_PACKED)
		.value("IOV_SCALAR_SPARSE", hwtHls::IOVectorizationType::IOV_SCALAR_SPARSE)
		.value("IOV_SCALAR_SPARSE_SYNCED", hwtHls::IOVectorizationType::IOV_SCALAR_SPARSE_SYNCED)
		.finalize();
	py::class_<hwtHls::IOVectorizationMd>(m, "IOVectorizationMd")
		.def(py::init<>())
		.def(py::init<IOVectorizationType, std::optional<unsigned>>())
		.def_readwrite("type", &IOVectorizationMd::type)
		.def_readwrite("laneCnt", &IOVectorizationMd::laneCnt)
		;
	py::class_<hwtHls::HwtHlsIoMetadata>(m, "HwtHlsIoMetadata")
		.def(py::init<>())
    	.def(py::init<IODirection,  // direction
    	              size_t,         // addrWidth
    	              size_t,         // readWordWidth
    	              size_t,         // writeWordWidth
    	              llvm::Function*,// otherThreadFn
    	              size_t,         // otherArgIndex
    	              bool,           // hasBlockingLoad
    	              bool,           // hasBlockingStore
    	              size_t,         // bufferCapacity
    	              MDTupleWithDeletedDelete*, // ioPropertyPath
    	              MDTupleWithDeletedDelete*, // latenciesFromPredecessorIo
    	              MDTupleWithDeletedDelete*, // ioProtocolMd
    	              std::optional<hwtHls::IOVectorizationMd> // ioVectorization
    	      >(),
    	      py::arg("direction"),
    	      py::arg("addrWidth"),
    	      py::arg("readWordWidth"),
    	      py::arg("writeWordWidth"),
    	      py::arg("otherThreadFn"),
    	      py::arg("otherArgIndex"),
    	      py::arg("hasBlockingLoad"),
    	      py::arg("hasBlockingStore"),
    	      py::arg("bufferCapacity"),
    	      py::arg("ioPropertyPath"),
    	      py::arg("latenciesFromPredecessorIo"),
    	      py::arg("ioProtocolMd"),
    	      py::arg("ioVectorization")
    	)
    	.def_readwrite("direction", &HwtHlsIoMetadata::direction)
    	.def_readwrite("addrWidth", &HwtHlsIoMetadata::addrWidth)
    	.def_readwrite("readWordWidth", &HwtHlsIoMetadata::readWordWidth)
    	.def_readwrite("writeWordWidth", &HwtHlsIoMetadata::writeWordWidth)
    	.def_readwrite("otherThreadFn", &HwtHlsIoMetadata::otherThreadFn)
    	.def_readwrite("otherArgIndex", &HwtHlsIoMetadata::otherArgIndex)
    	.def_readwrite("hasBlockingLoad", &HwtHlsIoMetadata::hasBlockingLoad)
    	.def_readwrite("hasBlockingStore", &HwtHlsIoMetadata::hasBlockingStore)
    	.def_readwrite("bufferCapacity", &HwtHlsIoMetadata::bufferCapacity)
    	.def_property("ioPropertyPath", [](hwtHls::HwtHlsIoMetadata & self) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(self.ioPropertyPath);
		}, [](hwtHls::HwtHlsIoMetadata & self, MDTupleWithDeletedDelete * v) {
			self.ioPropertyPath = reinterpret_cast<llvm::MDTuple*>(v);
		})
    	.def_property("latenciesFromPredecessorIo", [](hwtHls::HwtHlsIoMetadata & self) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(self.latenciesFromPredecessorIo);
		}, [](hwtHls::HwtHlsIoMetadata & self, MDTupleWithDeletedDelete * v) {
			self.latenciesFromPredecessorIo = reinterpret_cast<llvm::MDTuple*>(v);
		})
	 	.def_property("ioProtocolMd", [](hwtHls::HwtHlsIoMetadata & self) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(self.ioProtocolMd);
		}, [](hwtHls::HwtHlsIoMetadata & self, MDTupleWithDeletedDelete * v) {
			self.ioProtocolMd = reinterpret_cast<llvm::MDTuple*>(v);
		})
		.def_readwrite("ioVectorization", &HwtHlsIoMetadata::ioVectorization)
		.def_readwrite("unparsedMd", &hwtHls::HwtHlsIoMetadata::unparsedMd) // this requires PYBIND11_MAKE_OPAQUE(std::vector<llvm::Metadata*>); otherwise
		// the access to property just returns new python list instance and it would not be possible to append to this vector from python
		.def("__eq__", [](const hwtHls::HwtHlsIoMetadata &V0, const hwtHls::HwtHlsIoMetadata & V1) { return V0 == V1;})
		.def("__repr__", &printToStr<HwtHlsIoMetadata>)
	    .def_readonly_static("METADATA_NAME", &HwtHlsIoMetadata::METADATA_NAME);
		;
	using HwtHlsIoMetadataSmallVector = llvm::SmallVector<hwtHls::HwtHlsIoMetadata>;
	py::class_<HwtHlsIoMetadataSmallVector>(m, "HwtHlsIoMetadataSmallVector")
		.def(py::init<>())
		.def("push_back", [](HwtHlsIoMetadataSmallVector * self, const HwtHlsIoMetadata & elm) {
			self->push_back(elm);
		})
		.def("__getitem__", [](HwtHlsIoMetadataSmallVector &V, int index) {
			if (index >= int(V.size()) || index < -int(V.size())) {
				throw std::runtime_error("IndexError");
			}
			if (index < 0) {
				return V[int(V.size()) + index];
			} else {
				return V[index];
			}
		})
		.def("__eq__", [](HwtHlsIoMetadataSmallVector &V0, HwtHlsIoMetadataSmallVector &V1) {
			return V0 == V1;
		})
		.def("__len__", [](HwtHlsIoMetadataSmallVector &V) { return V.size(); })
		.def("__iter__", [](HwtHlsIoMetadataSmallVector &V) {
			return py::make_iterator(V.begin(), V.end());
		}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */
		;

    py::bind_vector<std::vector<llvm::Metadata*>>(m, "VectorMetadataPtr");
	py::implicitly_convertible<py::list, std::vector<llvm::Metadata*>>();

	m.def("HwtHlsIoMetadata_get", [](llvm::Function & F) { return HwtHlsIoMetadata_get(F); });
	m.def("HwtHlsIoMetadata_get", [](llvm::Function & F, size_t argI) { return HwtHlsIoMetadata_get(F, argI); });
    m.def("HwtHlsIoMetadata_set", [](llvm::Function & F, const llvm::SmallVector<HwtHlsIoMetadata> & mds) { HwtHlsIoMetadata_set(F, mds);});

}

void register_ThreadSplitSectionMetadata(pybind11::module_ & m) {
	py::class_<hwtHls::ThreadSplitSectionMetadata> _ThreadSplitSectionMetadata(m, "ThreadSplitSectionMetadata");
	    _ThreadSplitSectionMetadata
			.def(py::init<>())
			.def(py::init<std::string, bool, bool, bool, bool, size_t, size_t>())
			.def_readwrite("name", &ThreadSplitSectionMetadata::name)
			.def_readwrite("aggregateInputs", &ThreadSplitSectionMetadata::aggregateInputs)
			.def_readwrite("beginMayBeAsync", &ThreadSplitSectionMetadata::beginMayBeAsync)
			.def_readwrite("aggregateOutputs", &ThreadSplitSectionMetadata::aggregateOutputs)
			.def_readwrite("endMayBeAsync", &ThreadSplitSectionMetadata::name)
			.def_readwrite("inputBufferSize", &ThreadSplitSectionMetadata::inputBufferCapacity)
			.def_readwrite("outputBufferSize", &ThreadSplitSectionMetadata::outputBufferCapacity)
			.def("toMetadata", [](hwtHls::ThreadSplitSectionMetadata & self, llvm::LLVMContext & Ctx) {
				return reinterpret_cast<MDNodeWithDeletedDelete*>(self.toMetadata(Ctx));
			})
			.def_static("fromMetadata", &ThreadSplitSectionMetadata::fromMetadata)
			.def_readonly_static("METADATA_NAME", &ThreadSplitSectionMetadata::METADATA_NAME)
			;
}

void register_ThreadExtractIoFsmMetadata(pybind11::module_ & m) {
    py::class_<hwtHls::ThreadExtractIoFsmMetadata> _ThreadExtractIoFsmMetadata(m, "ThreadExtractIoFsmMetadata");
    _ThreadExtractIoFsmMetadata
		//.def(py::init<>())
		.def_readonly_static("METADATA_NAME", &ThreadExtractIoFsmMetadata::METADATA_NAME)
	;
}

void register_MetadataThreadHwtComponent(pybind11::module_ & m) {
	py::class_<hwtHls::MetadataPyObjectPath> _MetadataPyObjectPath(m, "MetadataPyObjectPath");
	_MetadataPyObjectPath.def_readwrite("value", &hwtHls::MetadataPyObjectPath::value);

	py::class_<hwtHls::IntStringTupleOrObjectPath> _IntStringTupleOrObjectPath(m, "IntStringTupleOrObjectPath");
	py::native_enum<hwtHls::IntStringTupleOrObjectPath::ValueT> (_IntStringTupleOrObjectPath, "ValueT", "enum.Enum")
		.value("V_NULL", hwtHls::IntStringTupleOrObjectPath::ValueT::V_NULL)
		.value("V_INT", hwtHls::IntStringTupleOrObjectPath::ValueT::V_INT)
		.value("V_STR", hwtHls::IntStringTupleOrObjectPath::ValueT::V_STR)
		.value("V_TUPLE", hwtHls::IntStringTupleOrObjectPath::ValueT::V_TUPLE)
		.value("V_OBJECT", hwtHls::IntStringTupleOrObjectPath::ValueT::V_OBJECT)
		.finalize();

	_IntStringTupleOrObjectPath
		.def(py::init<>())
		.def(py::init<const llvm::APInt &>())
		.def(py::init<uint64_t>())
		.def(py::init<const std::string &>())
		.def(py::init<const std::vector<IntStringTupleOrObjectPath> & >())
		.def(py::init<const MetadataPyObjectPath &>())
		.def_readwrite("valT", &hwtHls::IntStringTupleOrObjectPath::valT)
		.def_readwrite("vInt", &hwtHls::IntStringTupleOrObjectPath::vInt)
		.def_readwrite("vStr", &hwtHls::IntStringTupleOrObjectPath::vStr)
		.def_readwrite("vTuple", &hwtHls::IntStringTupleOrObjectPath::vTuple)
		.def_readwrite("vObj", &hwtHls::IntStringTupleOrObjectPath::vObj)
		;

	py::class_<hwtHls::MetadataThreadHwtComponent> _MetadataThreadHwtComponent(m, "MetadataThreadHwtComponent");
	_MetadataThreadHwtComponent
		.def(py::init<>())
		.def_readwrite("constructor", &hwtHls::MetadataThreadHwtComponent::constructor)
	    .def_readwrite("constructorArgs", &hwtHls::MetadataThreadHwtComponent::constructorArgs)
	    .def_readwrite("constructorKwargs", &hwtHls::MetadataThreadHwtComponent::constructorKwargs)
	    .def_readwrite("hwParams", &hwtHls::MetadataThreadHwtComponent::hwParams)
	    .def_readwrite("ioMappingOverride", &hwtHls::MetadataThreadHwtComponent::ioMappingOverride)
		.def_static("get", &hwtHls::MetadataThreadHwtComponent::get)
		.def("set", &hwtHls::MetadataThreadHwtComponent::set);

}

void register_StreamChannelFormatInfo(pybind11::module_ & m) {
	py::native_enum<hwtHls::ByteEnableEncoding> (m, "ByteEnableEncoding", "enum.Enum")
		.value("BEE_NONE", hwtHls::ByteEnableEncoding::BEE_NONE)
		.value("BEE_MASK", hwtHls::ByteEnableEncoding::BEE_MASK)
		.value("BEE_ENABLE_PLUS_EMPTY", hwtHls::ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY)
		.finalize();

	py::native_enum<hwtHls::FramingSignalizationEconding>(m, "FramingSignalizationEconding", "enum.Enum")
		.value("FRAMING_NONE", hwtHls::FramingSignalizationEconding::FRAMING_NONE)
		.value("FRAMING_EOF", hwtHls::FramingSignalizationEconding::FRAMING_EOF)
		.value("FRAMING_SOF_EOF", hwtHls::FramingSignalizationEconding::FRAMING_SOF_EOF)
		.finalize();

	py::class_<hwtHls::StreamChannelProps> _StreamChannelProps(m, "StreamChannelProps");
	_StreamChannelProps
		.def_readonly_static("METADATA_NAME_TMP_VAR_DATA_OFFSET", &hwtHls::StreamChannelProps::METADATA_NAME_TMP_VAR_DATA_OFFSET);


	py::class_<hwtHls::StreamChannelFormatInfo> _StreamChannelFormatInfo(m, "StreamChannelFormatInfo");
	_StreamChannelFormatInfo
	.def_readonly("segmentCnt", &hwtHls::StreamChannelFormatInfo::segmentCnt)
	.def_readonly("dataWidth", &hwtHls::StreamChannelFormatInfo::dataWidth)
	.def_readonly("byteWidth", &hwtHls::StreamChannelFormatInfo::byteWidth)
	.def_readonly("supportZLP", &hwtHls::StreamChannelFormatInfo::supportZLP)
	.def_readonly("errorWidth", &hwtHls::StreamChannelFormatInfo::errorWidth)
	.def_readonly("byteEnableEncoding", &hwtHls::StreamChannelFormatInfo::byteEnableEncoding)
	.def_readonly("framingEncoding", &hwtHls::StreamChannelFormatInfo::framingEncoding)
	.def("hasSoF", &hwtHls::StreamChannelFormatInfo::hasSoF)
	.def("hasEoF", &hwtHls::StreamChannelFormatInfo::hasEoF)
	.def("hasMask", &hwtHls::StreamChannelFormatInfo::hasMask)
	.def("hasEnable", &hwtHls::StreamChannelFormatInfo::hasEnable)
	.def("hasEmpty", &hwtHls::StreamChannelFormatInfo::hasEmpty)
	.def("hasError", &hwtHls::StreamChannelFormatInfo::hasError)
	.def("getOffsetOfError", &hwtHls::StreamChannelFormatInfo::getOffsetOfError)//
	.def("getOffsetOfSoF", &hwtHls::StreamChannelFormatInfo::getOffsetOfSoF)//
	.def("getOffsetOfEoF", &hwtHls::StreamChannelFormatInfo::getOffsetOfEoF)//
	.def("getOffsetOfEmpty", &hwtHls::StreamChannelFormatInfo::getOffsetOfEmpty)//
	.def("getOffsetOfMask", &hwtHls::StreamChannelFormatInfo::getOffsetOfMask)//
	.def("getOffsetOfEnable", &hwtHls::StreamChannelFormatInfo::getOffsetOfEnable)	//
	.def("getWidthOfEmpty", &hwtHls::StreamChannelFormatInfo::getWidthOfEmpty)//
	.def_static("getWidthOfEmptyForData", &hwtHls::StreamChannelFormatInfo::getWidthOfEmptyForData)
	.def("getWidthOfMask", &hwtHls::StreamChannelFormatInfo::getWidthOfMask)//
	.def("getWidthOfMaskForData", &hwtHls::StreamChannelFormatInfo::getWidthOfMaskForData)//
	.def("getWidthOfFramingEncoding", &hwtHls::StreamChannelFormatInfo::getWidthOfFramingEncoding)//
	.def("getWidthOfBusWord", &hwtHls::StreamChannelFormatInfo::getWidthOfBusWord)//
	.def_static("findInMetadata", &hwtHls::StreamChannelFormatInfo::findInMetadata)
	.def_readonly_static("METADATA_NAME", &hwtHls::StreamChannelFormatInfo::METADATA_NAME)
	.def_static("findOptionalInMetadata",  [](llvm::Argument &ioArg) {
		return hwtHls::StreamChannelFormatInfo::findOptionalInMetadata(ioArg);
	})
	;
}

void register_MetadataIoAxiMM(pybind11::module_ & m) {
	py::native_enum<hwtHls::MemoryOrdering> (m, "MemoryOrdering", "enum.Enum")
		.value("MEMORDERING_NONE", hwtHls::MemoryOrdering::MEMORDERING_NONE)
		.value("MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM", hwtHls::MemoryOrdering::MEMORDERING_MUST_WAIT_FOR_WRITE_CONFIRM)
		.finalize();

	py::class_<MetadataIoAxiMM>(m, "MetadataIoAxiMM")
		.def(py::init<>())
		.def(py::init<
				const llvm::APInt&,  // arDefault
                const llvm::APInt&,  // rDefault
                const llvm::APInt&,  // awDefault
                const llvm::APInt&,  // wDefault
                const llvm::APInt&,  // bDefault
                const std::pair<size_t, size_t>&,  // aId
                const std::pair<size_t, size_t>&,  // bId
                const std::pair<size_t, size_t>&,  // rId
                const std::pair<size_t, size_t>&,  // wId
                const std::pair<size_t, size_t>&,  // addr
                const std::pair<size_t, size_t>&,  // len
                const std::pair<size_t, size_t>&,  // rData
                const std::pair<size_t, size_t>&,   // wData
				size_t ,  // dataWidth
	            unsigned, // latencyArToR,
				unsigned, // latencyAwToW,
	            unsigned, // latencyWToB,
	            unsigned, // latencyBToR
				hwtHls::MemoryOrdering  // memOrdering
				>(),
				py::arg("arDefault"),
				py::arg("rDefault"),
				py::arg("awDefault"),
				py::arg("wDefault"),
				py::arg("bDefault"),
				py::arg("aId"),
				py::arg("bId"),
				py::arg("rId"),
				py::arg("wId"),
				py::arg("addr"),
				py::arg("len"),
				py::arg("rData"),
				py::arg("wData"),
				py::arg("dataWidth"),
				py::arg("latencyArToR"),
				py::arg("latencyAwToW"),
				py::arg("latencyWToB"),
				py::arg("latencyBToR"),
				py::arg("memOrdering")
		)
		.def_readwrite("arDefault", &MetadataIoAxiMM::arDefault)
	    .def_readwrite("rDefault", &MetadataIoAxiMM::rDefault)
	    .def_readwrite("awDefault", &MetadataIoAxiMM::awDefault)
	    .def_readwrite("wDefault", &MetadataIoAxiMM::wDefault)
	    .def_readwrite("bDefault", &MetadataIoAxiMM::bDefault)
	    .def_readwrite("aId", &MetadataIoAxiMM::aId)
	    .def_readwrite("bId", &MetadataIoAxiMM::bId)
	    .def_readwrite("rId", &MetadataIoAxiMM::rId)
	    .def_readwrite("wId", &MetadataIoAxiMM::wId)
	    .def_readwrite("addr", &MetadataIoAxiMM::addr)
	    .def_readwrite("len", &MetadataIoAxiMM::len)
	    .def_readwrite("rData", &MetadataIoAxiMM::rData)
	    .def_readwrite("wData", &MetadataIoAxiMM::wData)
		.def_readwrite("dataWidth", &MetadataIoAxiMM::dataWidth)
		.def_readwrite("latencyArToR", &MetadataIoAxiMM::latencyArToR)
		.def_readwrite("latencyAwToW", &MetadataIoAxiMM::latencyAwToW)
		.def_readwrite("latencyWToB", &MetadataIoAxiMM::latencyWToB)
		.def_readwrite("latencyBToR", &MetadataIoAxiMM::latencyBToR)
		.def_readwrite("memOrdering", &MetadataIoAxiMM::memOrdering)
		.def("toMetadata", [](hwtHls::MetadataIoAxiMM & self, llvm::LLVMContext & Ctx) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(self.toMetadata(Ctx));
		}, py::return_value_policy::reference_internal)
		.def_static("fromMetadata", [](const MDTupleWithDeletedDelete &md) {
			return MetadataIoAxiMM::fromMetadata(md);
		});
}
void register_MDNode(pybind11::module_ & m) {
	py::class_<llvm::Metadata, std::unique_ptr<llvm::Metadata, py::nodelete>> Metadata(m, "Metadata");
	Metadata
		.def("asMetadata", &asMetadata<llvm::Metadata>, py::return_value_policy::reference_internal)
		.def("__repr__", &printToStr<llvm::Metadata>);

	// :attention: all pybind11 bindings for functions using llvm::MDNode must be overriden to use this class instead
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
	m.def("MetadataToValueAsMetadata", [](llvm::Metadata * MD) {
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
		.def("getString", &llvm::MDString::getString)
		.def("asMetadata", &asMetadata<llvm::MDString>, py::return_value_policy::reference_internal)
		.def("__repr__", &printToStr<llvm::MDString>);
	m.def("MetadataAsMDString", [](llvm::Metadata * MD) {
		return dyn_cast<llvm::MDString>(MD);
	}, py::return_value_policy::reference_internal);

	py::implicitly_convertible<MDTupleWithDeletedDelete, llvm::Metadata>();
	py::implicitly_convertible<MDTupleWithDeletedDelete, MDNodeWithDeletedDelete>();
	py::implicitly_convertible<MDNodeWithDeletedDelete, llvm::Metadata>();
	py::implicitly_convertible<llvm::MDString, llvm::Metadata>();
	//py::implicitly_convertible<llvm::ConstantAsMetadata, llvm::Metadata>();
	//py::implicitly_convertible<llvm::ValueAsMetadata, llvm::Metadata>();
	//py::implicitly_convertible<llvm::MDString, llvm::Metadata>();
	register_HwtHlsIoMetadata(m);
	register_ThreadSplitSectionMetadata(m);
	register_ThreadExtractIoFsmMetadata(m);
	register_MetadataThreadHwtComponent(m);
	register_MetadataIoAxiMM(m);
	register_StreamChannelFormatInfo(m);
}

}
