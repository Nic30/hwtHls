#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>

#include <llvm/IR/Metadata.h>

using namespace llvm;

namespace hwtHls {

const std::string METADATA_NAME_hwtHlsIo = "hwtHls.io";

bool HwtHlsIoMetadata::isDefaultValue() const {
	return direction == IO_DIR_UNRESOLVED && addrWidth == 0
			&& otherThreadFn == nullptr;
}

HwtHlsIoMetadata HwtHlsIoMetadata_get(llvm::Metadata &hwtHlsIOItem) {
	MDTuple *aMD = dyn_cast<MDTuple>(&hwtHlsIOItem);
	assert(aMD->getNumOperands() == 4);
	HwtHlsIoMetadata aMd;
	auto dir = cast<MDString>(aMD->getOperand(0).get())->getString();
	if (dir.equals("UNRESOLVED")) {
		aMd.direction = IO_DIR_UNRESOLVED;
	} else if (dir.equals("IN")) {
		aMd.direction = IO_DIR_IN;
	} else if (dir.equals("OUT")) {
		aMd.direction = IO_DIR_OUT;
	} else {
		throw std::runtime_error(
				("HwtHlsIoMetadata_get invalid value for direction: " + dir).str());
	}

	auto aw = cast<ValueAsMetadata>(aMD->getOperand(1).get())->getValue();
	aMd.addrWidth = dyn_cast<ConstantInt>(aw)->getZExtValue();

	auto ofn = dyn_cast<ValueAsMetadata>(aMD->getOperand(2).get());
	aMd.otherThreadFn = dyn_cast<Function>(ofn->getValue());

	auto oai = cast<ValueAsMetadata>(aMD->getOperand(3).get())->getValue();
	aMd.otherArgIndex = dyn_cast<ConstantInt>(oai)->getZExtValue();
	if (aMd.otherThreadFn) {
		if (aMd.otherArgIndex >= aMd.otherThreadFn->arg_size()) {
			throw std::runtime_error(
					"HwtHlsIoMetadata_get metadata references non existing argument");
		}
	}
	return aMd;
}

std::optional<HwtHlsIoMetadata> HwtHlsIoMetadata_get(llvm::Function &F,
		size_t argI) {
	auto MD = F.getMetadata(METADATA_NAME_hwtHlsIo);
	if (MD) {
		assert(MD->getNumOperands() == 2 && "expected format for distinct MD");
		assert(
				MD == MD->getOperand(0).get()
						&& "expected format for distinct MD");
		MDTuple *HwtHlsIoMetadataMDTuple = dyn_cast<MDTuple>(
				MD->getOperand(1).get());
		assert(HwtHlsIoMetadataMDTuple->getNumOperands() == F.arg_size());
		assert(argI < F.arg_size());
		return HwtHlsIoMetadata_get(
				*HwtHlsIoMetadataMDTuple->getOperand(argI).get());
	}
	return {};
}

llvm::SmallVector<HwtHlsIoMetadata> HwtHlsIoMetadata_get(llvm::Function &F) {
	llvm::SmallVector<HwtHlsIoMetadata> res;
	auto MD = F.getMetadata(METADATA_NAME_hwtHlsIo);
	if (MD) {
		assert(MD->getNumOperands() == 2 && "expected format for distinct MD");
		assert(
				MD == MD->getOperand(0).get()
						&& "expected format for distinct MD");
		MDTuple *HwtHlsIoMetadataMDTuple = dyn_cast<MDTuple>(
				MD->getOperand(1).get());
		for (auto &_aMD : HwtHlsIoMetadataMDTuple->operands()) {
			auto aMd = HwtHlsIoMetadata_get(*_aMD.get());
			res.push_back(aMd);
		}
	} else {
		for (auto &A : F.args())
			res.push_back(
					HwtHlsIoMetadata(IO_DIR_UNRESOLVED, 0, nullptr,
							A.getArgNo()));
	}
	return res;
}

void HwtHlsIoMetadata_set(llvm::Function &F,
		const llvm::SmallVector<HwtHlsIoMetadata> &mds) {
	llvm::SmallVector<Metadata*> MDs;
	auto &Ctx = F.getContext();
	bool allAreJustDefaultValue = true;
	for (auto &md : mds) {
		if (!md.isDefaultValue()) {
			allAreJustDefaultValue = false;
			break;
		}
	}
	if (allAreJustDefaultValue) {
		F.setMetadata(METADATA_NAME_hwtHlsIo, nullptr);
		return;
	}

	for (auto &md : mds) {
		MDNode *MD = nullptr;
		const char *dir = nullptr;
		switch (md.direction) {
		case IO_DIR_UNRESOLVED:
			dir = "UNRESOLVED";
			break;
		case IO_DIR_IN:
			dir = "IN";
			break;
		case IO_DIR_OUT:
			dir = "OUT";
			break;
		default:
			assert(false && "Invalid value for direction");
		}
		Value *_otherThreadFn =
				md.otherThreadFn ?
						(Value*)md.otherThreadFn :
						(Value*)ConstantPointerNull::get(PointerType::get(Ctx, 0));
		Metadata *otherThreadFn = ValueAsMetadata::get(_otherThreadFn);
		auto *u64 = IntegerType::get(Ctx, 64);
		Metadata *addrWidth = ValueAsMetadata::get(
				ConstantInt::get(u64, md.addrWidth));
		Metadata *otherArgIndex = ValueAsMetadata::get(
				ConstantInt::get(u64, md.otherArgIndex));
		std::array<Metadata*, 4> mdArgs = { MDString::get(Ctx, dir), addrWidth,
				otherThreadFn, otherArgIndex, };
		MD = MDNode::get(Ctx, mdArgs);
		MDs.push_back(MD);
	}

	std::vector<llvm::Metadata*> MDs_tmp;
	// llvm::MDNode::getTemporary(Context, {}).get()
	MDs_tmp.push_back(nullptr);

	MDNode *HwtHlsIoMetadataMDTuple = MDNode::get(Ctx, MDs);
	MDs_tmp.push_back(HwtHlsIoMetadataMDTuple);
	auto FnMDDistinct = llvm::MDNode::get(Ctx, MDs_tmp);
	FnMDDistinct->replaceOperandWith(0, FnMDDistinct);
	F.setMetadata(METADATA_NAME_hwtHlsIo, FnMDDistinct);
}

}
