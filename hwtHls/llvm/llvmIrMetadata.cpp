#include <hwtHls/llvm/llvmIrMetadata.h>

#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <hwtHls/llvm/llvmIrCommon.h>
#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

#include <pybind11/native_enum.h>

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


void register_HwtHlsIoMetadata(pybind11::module_ & m) {
	py::native_enum<hwtHls::IODirection> (m, "IODirection", "enum.Enum")
		.value("IO_DIR_IN", hwtHls::IODirection::IO_DIR_IN)
		.value("IO_DIR_OUT", hwtHls::IODirection::IO_DIR_OUT)
		.value("IO_DIR_UNRESOLVED", hwtHls::IODirection::IO_DIR_UNRESOLVED)
		.finalize();
	py::class_<hwtHls::HwtHlsIoMetadata>(m, "HwtHlsIoMetadata")
		.def(py::init<>())
    	.def(py::init<IODirection,  // direction
    	              size_t,         // addrWidth
    	              size_t,         // readWordWidth
    	              size_t,         // writeWordWidth
    	              bool,           // isBlocking
    	              llvm::Function*,// otherThreadFn
    	              size_t,         // otherArgIndex
					  size_t,         // bufferCapacity
    	              MDTupleWithDeletedDelete*, // ioPropertyPath
    	              MDTupleWithDeletedDelete*, // latenciesFromPredecessorIo
    	              MDTupleWithDeletedDelete*, // protocolSpecificMetadata
					  MDTupleWithDeletedDelete*, // streamIoMd
					  MDTupleWithDeletedDelete*> // ioFsmExtractMd
    	      (),
    	      py::arg("direction"),
    	      py::arg("addrWidth"),
    	      py::arg("readWordWidth"),
    	      py::arg("writeWordWidth"),
    	      py::arg("isBlocking"),
    	      py::arg("otherThreadFn"),
    	      py::arg("otherArgIndex"),
			  py::arg("bufferCapacity"),
    	      py::arg("ioPropertyPath"),
    	      py::arg("latenciesFromPredecessorIo"),
    	      py::arg("protocolSpecificMetadata"),
			  py::arg("streamIoMd"),
			  py::arg("ioFsmExtractMd")
    	)
    	.def_readwrite("direction", &HwtHlsIoMetadata::direction)
    	.def_readwrite("addrWidth", &HwtHlsIoMetadata::addrWidth)
    	.def_readwrite("readWordWidth", &HwtHlsIoMetadata::readWordWidth)
    	.def_readwrite("writeWordWidth", &HwtHlsIoMetadata::writeWordWidth)
    	.def_readwrite("otherThreadFn", &HwtHlsIoMetadata::otherThreadFn)
    	.def_readwrite("otherArgIndex", &HwtHlsIoMetadata::otherArgIndex)
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
	 	.def_property("protocolSpecificMetadata", [](hwtHls::HwtHlsIoMetadata & self) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(self.protocolSpecificMetadata);
		}, [](hwtHls::HwtHlsIoMetadata & self, MDTupleWithDeletedDelete * v) {
			self.protocolSpecificMetadata = reinterpret_cast<llvm::MDTuple*>(v);
		})
		.def_property("streamIoMd", [](hwtHls::HwtHlsIoMetadata & self) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(self.streamIoMd);
		}, [](hwtHls::HwtHlsIoMetadata & self, MDTupleWithDeletedDelete * v) {
			self.streamIoMd = reinterpret_cast<llvm::MDTuple*>(v);
		})
		.def_property("ioFsmExtractMd", [](hwtHls::HwtHlsIoMetadata & self) {
			return reinterpret_cast<MDTupleWithDeletedDelete*>(self.ioFsmExtractMd);
		}, [](hwtHls::HwtHlsIoMetadata & self, MDTupleWithDeletedDelete * v) {
			self.ioFsmExtractMd = reinterpret_cast<llvm::MDTuple*>(v);
		})
		.def("__eq__", [](const hwtHls::HwtHlsIoMetadata &V0, const hwtHls::HwtHlsIoMetadata & V1) { return V0 == V1;})
		.def("__repr__", &printToStr<HwtHlsIoMetadata>)
	    .def_readonly_static("METADATA_NAME", &HwtHlsIoMetadata::METADATA_NAME);
		;
	using HwtHlsIoMetadataSmallVector = llvm::SmallVector<hwtHls::HwtHlsIoMetadata>;
	py::class_<HwtHlsIoMetadataSmallVector>(m, "HwtHlsIoMetadataSmallVector")
		.def(py::init<>())
		.def("push_back", &HwtHlsIoMetadataSmallVector::push_back)
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
	m.def("HwtHlsIoMetadata_get", [](llvm::Function & F) { return HwtHlsIoMetadata_get(F); });
    m.def("HwtHlsIoMetadata_set", [](llvm::Function & F, const llvm::SmallVector<HwtHlsIoMetadata> & mds) { HwtHlsIoMetadata_set(F, mds);});

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

	py::enum_<hwtHls::ByteEnableEncoding> (m, "ByteEnableEncoding")
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
	.def_static("findOptionalInMetadata",  [](llvm::Argument &ioArg) {
		return hwtHls::StreamChannelFormatInfo::findOptionalInMetadata(ioArg);
	})
	;
}

}
