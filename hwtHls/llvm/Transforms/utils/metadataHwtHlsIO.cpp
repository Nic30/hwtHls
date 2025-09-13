#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>

#include <llvm/IR/Metadata.h>
#include <llvm/ADT/SmallPtrSet.h>

using namespace llvm;

namespace hwtHls {

IODirection IODirection_reverse(IODirection d) {
	switch (d) {
	case IO_DIR_IN:
		return IO_DIR_OUT;
	case IO_DIR_OUT:
		return IO_DIR_IN;
	case IO_DIR_UNRESOLVED:
		return IO_DIR_UNRESOLVED;
	default:
		llvm_unreachable("IODirection_reverse invalid value");
	}
}

const char* IODirection_toString(IODirection d) {
	switch (d) {
	case IO_DIR_UNRESOLVED:
		return "UNRESOLVED";
		break;
	case IO_DIR_IN:
		return "IN";
		break;
	case IO_DIR_OUT:
		return "OUT";
		break;
	default:
		assert(false && "Invalid value for direction");
	}
	return "INVALID";
}

const std::string HwtHlsIoMetadata::METADATA_NAME = "hwtHls.io";

bool HwtHlsIoMetadata::isOut() const {
	return direction == IODirection::IO_DIR_OUT;
}
bool HwtHlsIoMetadata::isDefaultValue() const {
	return direction == IO_DIR_UNRESOLVED && addrWidth == 0
			&& otherThreadFn == nullptr;
}

void HwtHlsIoMetadata::consystencyCheck() const {
	if (otherThreadFn) {
		if (otherArgIndex >= otherThreadFn->arg_size()) {
			throw std::runtime_error(
					"HwtHlsIoMetadata_get metadata references non existing argument");
		}
	}
}

bool HwtHlsIoMetadata::operator==(const HwtHlsIoMetadata &other) const {
	//return memcmp(this, &other, sizeof *this) == 0;
	return (direction == other.direction && //
			addrWidth == other.addrWidth && //
			readWordWidth == other.readWordWidth && //
			writeWordWidth == other.writeWordWidth && //
			isBlocking == other.isBlocking && //
			otherThreadFn == other.otherThreadFn && //
			otherArgIndex == other.otherArgIndex);
}

void HwtHlsIoMetadata::print(llvm::raw_ostream &O, bool IsForDebug) const {
	O << "<HwtHlsIoMetadata " << IODirection_toString(direction);
	O << " addrWidth=" << addrWidth << " readWordWidth=" << readWordWidth;
	O << " writeWordWidth=" << writeWordWidth << " isBlocking=" << isBlocking
			<< " otherThreadFn=";
	if (otherThreadFn) {
		O << otherThreadFn->getName();
	} else {
		O << "null";
	}
	O << " otherArgIndex=" << otherArgIndex << ">";
}

HwtHlsIoMetadata HwtHlsIoMetadata::fromMetadata(llvm::Metadata &hwtHlsIOItem) {
	MDTuple *aMD = dyn_cast<MDTuple>(&hwtHlsIOItem);
	assert(aMD->getNumOperands() == 13);
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
	auto getMdInt = [&aMD](size_t argI) {
		auto v = cast<ValueAsMetadata>(aMD->getOperand(argI).get())->getValue();
		assert(isa<ConstantInt>(v));
		return dyn_cast<ConstantInt>(v)->getZExtValue();
	};
	aMd.addrWidth = getMdInt(1);
	aMd.readWordWidth = getMdInt(2);
	aMd.writeWordWidth = getMdInt(3);
	aMd.isBlocking = getMdInt(4);
	auto ofn = dyn_cast<ValueAsMetadata>(aMD->getOperand(5).get());
	aMd.otherThreadFn = dyn_cast<Function>(ofn->getValue());
	aMd.otherArgIndex = getMdInt(6);
	aMd.bufferCapacity = getMdInt(7);
	aMd.ioPropertyPath = dyn_cast<MDTuple>(aMD->getOperand(8).get());
	aMd.latenciesFromPredecessorIo = dyn_cast<MDTuple>(
			aMD->getOperand(9).get());
	aMd.protocolSpecificMetadata = dyn_cast<MDTuple>(aMD->getOperand(10).get());
	aMd.streamIoMd = dyn_cast<MDTuple>(aMD->getOperand(11).get());
	aMd.ioFsmExtractMd = dyn_cast<MDTuple>(aMD->getOperand(12).get());
	return aMd;
}

void HwtHlsIoMetadata::setLatenciesFromPredecessorIo(llvm::LLVMContext &Ctx,
		llvm::ArrayRef<int> _latenciesFromPredecessorIo) {
	if (_latenciesFromPredecessorIo.empty()) {
		latenciesFromPredecessorIo = nullptr;
		return;
	}

	SmallVector<Metadata*> mds;
	auto *i32 = IntegerType::get(Ctx, 32);
	for (auto lat : _latenciesFromPredecessorIo) {
		auto md = ValueAsMetadata::get(ConstantInt::get(i32, lat));
		mds.push_back(md);
	}
	latenciesFromPredecessorIo = MDTuple::getDistinct(Ctx, mds);
}

void HwtHlsIoMetadata::getLatenciesFromPredecessorIo(
		llvm::SmallVector<int> &_latenciesFromPredecessorIo) {
	assert(
			latenciesFromPredecessorIo
					&& "It should be checked that there any before call of this fn");
	for (const auto& md : latenciesFromPredecessorIo->operands()) {
		auto v = cast<ValueAsMetadata>(md.get())->getValue();
		assert(isa<ConstantInt>(v));
		int vAsInt = dyn_cast<ConstantInt>(v)->getSExtValue();
		_latenciesFromPredecessorIo.push_back(vAsInt);
	}
}

std::optional<HwtHlsIoMetadata> HwtHlsIoMetadata_get(const llvm::Function &F,
		size_t argI) {
	auto MD = F.getMetadata(HwtHlsIoMetadata::METADATA_NAME);
	if (MD) {
		MDTuple *HwtHlsIoMetadataMDTuple = dyn_cast<MDTuple>(MD);
		assert(
				HwtHlsIoMetadataMDTuple && HwtHlsIoMetadataMDTuple->isDistinct()
						&& HwtHlsIoMetadataMDTuple->getNumOperands()
								== F.arg_size()
						&& "expected format for distinct MD");
		if (argI < F.arg_size())
			return HwtHlsIoMetadata::fromMetadata(
					*HwtHlsIoMetadataMDTuple->getOperand(argI).get());
	}
	return {};
}

void HwtHlsIoMetadata_set(llvm::Function &F, size_t argI,
		const HwtHlsIoMetadata &md) {
	auto MD = F.getMetadata(HwtHlsIoMetadata::METADATA_NAME);
	assert(MD && "HwtHlsIoMetadata is required");
	assert(
			MD->getNumOperands() == F.arg_size()
					&& "HwtHlsIoMetadata expected distinct tuple of items for every function arg");
	MDTuple *HwtHlsIoMetadataMDTuple = dyn_cast<MDTuple>(MD);
	assert(argI < F.arg_size());

	std::vector<llvm::Metadata*> MDs_tmp;
	for (auto &md : HwtHlsIoMetadataMDTuple->operands()) {
		auto mdNode = dyn_cast<MDNode>(md.get());
		assert(mdNode);
		MDs_tmp.push_back(mdNode);
	}

	auto newArgMd = md.asMetadata(F.getContext());
	MDs_tmp[argI] = newArgMd;
	MDNode *newIoMdTuple = MDNode::getDistinct(F.getContext(), MDs_tmp);
	F.setMetadata(HwtHlsIoMetadata::METADATA_NAME, newIoMdTuple);
}

std::pair<llvm::Type*, llvm::Type*> getLoadOrStoreElementType(
		const llvm::Argument &arg) {
	Type *loadTy = nullptr;
	Type *storeTy = nullptr;
	for (auto *u : arg.users()) {
		if (auto ui = dyn_cast<Instruction>(u)) {
			auto lst = getLoadOrStoreElementType(*ui);
			if (lst.first) {
				if (loadTy) {
					assert(lst.first == loadTy);
				} else {
					loadTy = lst.first;
				}
			}
			if (lst.second) {
				if (storeTy) {
					assert(lst.second == storeTy);
				} else {
					storeTy = lst.second;
				}
			}
		}
	}
	return {loadTy, storeTy};
}

std::pair<llvm::Type*, llvm::Type*> getLoadOrStoreElementType(
		const llvm::Instruction &I) {
	if (auto Ld = dyn_cast<LoadInst>(&I)) {
		return {Ld->getAccessType(), nullptr};
	} else if (auto St = dyn_cast<StoreInst>(&I)) {
		return {nullptr, St->getAccessType()};
	} else if (auto gep = dyn_cast<GetElementPtrInst>(&I)) {
		for (auto u : gep->users()) {
			if (auto ui = dyn_cast<Instruction>(u)) {
				return getLoadOrStoreElementType(*ui);
			}
		}

	}
	return {nullptr, nullptr};
}

llvm::SmallVector<HwtHlsIoMetadata> HwtHlsIoMetadata_get(
		const llvm::Function &F) {
	llvm::SmallVector<HwtHlsIoMetadata> res;
	auto MD = F.getMetadata(HwtHlsIoMetadata::METADATA_NAME);
	if (MD) {
		assert(
				MD->getNumOperands() == F.arg_size()
						&& "HwtHlsIoMetadata expected to be tuple with item for each function argument");
		MDTuple *HwtHlsIoMetadataMDTuple = dyn_cast<MDTuple>(MD);
		assert(
				HwtHlsIoMetadataMDTuple && HwtHlsIoMetadataMDTuple->isDistinct()
						&& "HwtHlsIoMetadata expected to be distinct tuple");
		for (auto &_aMD : HwtHlsIoMetadataMDTuple->operands()) {
			auto aMd = HwtHlsIoMetadata::fromMetadata(*_aMD.get());
			res.push_back(aMd);
		}
	} else {
		for (auto &A : F.args()) {
			auto ldStTy = getLoadOrStoreElementType(A);
			res.push_back(
					HwtHlsIoMetadata(IO_DIR_UNRESOLVED, 0,
							ldStTy.first ?
									ldStTy.first->getIntegerBitWidth() : 0,
							ldStTy.second ?
									ldStTy.second->getIntegerBitWidth() : 0,
							true, nullptr, A.getArgNo(), 0, nullptr, nullptr, nullptr,
							nullptr, nullptr));
		}
	}
	return res;
}

llvm::MDNode* HwtHlsIoMetadata::asMetadata(LLVMContext &Ctx) const {
	const char *dir = IODirection_toString(direction);
	Value *_otherThreadFn =
			otherThreadFn ?
					(Value*) otherThreadFn :
					(Value*) ConstantPointerNull::get(PointerType::get(Ctx, 0));
	auto _isBlocking = ConstantInt::get(IntegerType::getInt1Ty(Ctx),
			isBlocking);
	auto *u64 = IntegerType::get(Ctx, 64);
	auto getU64md = [u64](uint64_t v) {
		return ValueAsMetadata::get(ConstantInt::get(u64, v));
	};
	auto getMd = [&Ctx](Metadata *md) {
		if (!md)
			md = ValueAsMetadata::get(
					ConstantPointerNull::get(PointerType::get(Ctx, 0)));
		return md;
	};
	std::array<Metadata*, 13> mdArgs = { //
			MDString::get(Ctx, dir), //
			getU64md(addrWidth),     //
			getU64md(readWordWidth), //
			getU64md(writeWordWidth), //
			ValueAsMetadata::get(_isBlocking),        //
			ValueAsMetadata::get(_otherThreadFn), //
			getU64md(otherArgIndex), //
			getU64md(bufferCapacity), //
			getMd(ioPropertyPath), //
			getMd(latenciesFromPredecessorIo), //
			getMd(protocolSpecificMetadata), //
			getMd(streamIoMd), //
			getMd(ioFsmExtractMd) };
	MDNode *MD = MDNode::get(Ctx, mdArgs);
	return MD;
}

void HwtHlsIoMetadata_set(llvm::Function &F,
		const llvm::SmallVector<HwtHlsIoMetadata> &mds) {
	assert(F.arg_size() == mds.size());
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
		F.setMetadata(HwtHlsIoMetadata::METADATA_NAME, nullptr);
		return;
	}

	for (auto &md : mds) {
		MDs.push_back(md.asMetadata(Ctx));
	}

	std::vector<llvm::Metadata*> MDs_tmp;
	MDNode *HwtHlsIoMetadataMDTuple = MDNode::getDistinct(Ctx, MDs);
	F.setMetadata(HwtHlsIoMetadata::METADATA_NAME, HwtHlsIoMetadataMDTuple);
}

bool verifyHwtHlsIoMetadata(const llvm::Module &M,
		bool allowFunctionsWithoutHwtHlsIoMetadata, llvm::raw_ostream *OS) {
	SmallPtrSet<const Function*, 32> fnsWithInvalidIoMd;
	bool isNonValid = false;
	for (auto &F : M) {
		if (F.isDeclaration())
			continue;
		auto ioMd = F.getMetadata(HwtHlsIoMetadata::METADATA_NAME);
		if (!ioMd) {
			if (!allowFunctionsWithoutHwtHlsIoMetadata) {
				isNonValid = true;
				fnsWithInvalidIoMd.insert(&F);
				if (OS) {
					(*OS) << "Function " << F.getName()
							<< " is missing HwtHlsIoMetadata\n";
				}
			}
		}
		const MDTuple *ioMdDistinctTuple = dyn_cast<MDTuple>(ioMd);
		if (!ioMdDistinctTuple || !ioMdDistinctTuple->isDistinct()) {
			isNonValid = true;
			fnsWithInvalidIoMd.insert(&F);
			if (OS) {
				(*OS) << "The distinct tuple of HwtHlsIoMetadata for function "
						<< F.getName()
						<< " should be in format like !0 = distinct !{!arg0Md, !arg1Md, ...}, but instead it is: "
						<< *ioMdDistinctTuple << "\n";
			}

		}
		if (ioMdDistinctTuple->getNumOperands() != F.arg_size()) {
			isNonValid = true;
			fnsWithInvalidIoMd.insert(&F);
			if (OS) {
				(*OS) << "The arg tuple of HwtHlsIoMetadata for function "
						<< F.getName()
						<< " should have item for each argument ("
						<< F.arg_size() << ") but has "
						<< ioMdDistinctTuple->getNumOperands()
						<< " item(s) instead\n";
			}
		}
	}
	for (auto &F : M) {
		if (F.isDeclaration())
			continue;
		if (fnsWithInvalidIoMd.contains(&F))
			continue;
		if (!F.hasMetadata(HwtHlsIoMetadata::METADATA_NAME))
			continue;
		auto mds = HwtHlsIoMetadata_get(F);
		size_t argI = 0;
		for (HwtHlsIoMetadata &md : mds) {
			if (md.otherThreadFn) {
				if (md.otherThreadFn->getParent() != &M) {
					isNonValid = true;
					if (OS) {
						(*OS) << "The function argument " << F.getName() << " "
								<< argI << "(";
						F.getArg(argI)->printAsOperand(*OS);
						(*OS)
								<< ") is connected to a function which does not exist in parent module\n";
					}
				}
				if (md.otherArgIndex >= md.otherThreadFn->arg_size()) {
					isNonValid = true;
					if (OS) {
						(*OS) << "The function argument " << F.getName() << " "
								<< argI << "(";
						F.getArg(argI)->printAsOperand(*OS);
						(*OS) << ") is connected to a function argument ";
						(*OS) << md.otherThreadFn->getName() << " "
								<< md.otherArgIndex
								<< " which does not exist\n";
					}
				}
				auto otherMd = HwtHlsIoMetadata_get(*md.otherThreadFn,
						md.otherArgIndex);
				if (md.direction
						!= IODirection_reverse(otherMd.value().direction)) {
					isNonValid = true;
					if (OS) {
						(*OS) << "The function argument " << F.getName() << " "
								<< argI << "(";
						F.getArg(argI)->printAsOperand(*OS);
						(*OS) << ") is connected to a function argument ";
						(*OS) << md.otherThreadFn->getName() << " "
								<< md.otherArgIndex << " ";
						md.otherThreadFn->getArg(md.otherArgIndex)->printAsOperand(
								*OS);
						(*OS) << " but they do not have opposite direction\n";
					}
				}

			}
			argI++;
		}

	}
	return isNonValid;
}

}
