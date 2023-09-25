#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_normalizeLookupTableIndex.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/GlobalVariable.h>

#define DEBUG_TYPE "simplifycfg2"

using namespace llvm;
namespace hwtHls {

static Value* cteateGEPtoGlobalData(IRBuilder<> &builder, BasicBlock &BB, Value *switch_tableidx,
		const SmallVector<Constant*> &romData) {
	auto *ArrayTy = ArrayType::get(romData[0]->getType(), romData.size());
	auto *newCRom = ConstantArray::get(ArrayTy, romData);
	auto *newArray = new GlobalVariable(*BB.getModule(), ArrayTy, /*isConstant=*/true, GlobalVariable::PrivateLinkage,
			newCRom, "switch.table.normalized");
	newArray->setUnnamedAddr(GlobalValue::UnnamedAddr::Global);
	// Set the alignment to that of an array items. We will be only loading one
	// value out of it.
	newArray->setAlignment(Align(1));
	// zext to assert the value is non negative
	auto *indexZext = builder.CreateZExt(switch_tableidx,
			Type::getIntNTy(BB.getContext(), switch_tableidx->getType()->getIntegerBitWidth() + 1),
			"switch.tableidx.zext");

	Value *GEPIndices[] = { builder.getInt32(0), indexZext };
	Value *newGep = builder.CreateInBoundsGEP(newArray->getValueType(), newArray, GEPIndices, "switch.gep");
	return newGep;
}

bool SimplifyCFG2Pass_normalizeLookupTableIndex(llvm::BasicBlock &BB) {
	// transform value stored in switch_ptr in order to use switch_tableidx_base as is
	using namespace llvm::PatternMatch;
	bool changed = false;
	for (Instruction &I : BB) {
		Value *switch_tableidx = nullptr;
		SmallVector<Constant*> romData;
		if (auto *switch_gep = dyn_cast<GEPOperator>(&I)) {
			// search for pattern like
			//
			//  %switch.tableidx = sub i7 %i0, -64
			//  %switch.tableidx.zext = zext i7 %switch.tableidx to i8
			//  %switch.gep = getelementptr inbounds [128 x i3], [128 x i3]* @switch.table.Popcount.mainThread, i32 0, i8 %switch.tableidx.zext
			//  %switch.load = load i3, i3* %switch.gep, align 1
			//  store volatile i3 %switch.load, i3 addrspace(2)* %o, align 1

			ConstantInt *switch_tableidx_off;
			unsigned ptrOpIndex = switch_gep->getPointerOperandIndex();
			Value *switch_ptr = switch_gep->getOperand(ptrOpIndex);
			Constant *switch_ptrConst;
			if (!match(switch_ptr, m_Constant(switch_ptrConst))) {
				continue;
			}
			switch_gep->dump();
			if (switch_gep->getNumIndices() != 2) {
				continue; // not implemented
			}
			uint64_t ind0;
			Value *switch_gep_ind0 = switch_gep->getOperand(ptrOpIndex + 1);
			if (!match(switch_gep_ind0, m_ConstantInt(ind0)) || ind0 != 0)
				continue;

			Value *switch_gep_ind1 = switch_gep->getOperand(ptrOpIndex + 2);
			if (match(switch_gep_ind1, m_ZExt(m_Sub(m_Value(switch_tableidx), m_ConstantInt(switch_tableidx_off))))) {
				size_t indexWidth = switch_tableidx->getType()->getIntegerBitWidth();
				int64_t indexOff = switch_tableidx_off->getSExtValue();

				LLVM_DEBUG(dbgs() << "table GEP detected\n");
				LLVM_DEBUG(dbgs() << I << "\n");
				if (GlobalValue *switch_arr = dyn_cast<GlobalValue>(switch_ptrConst)) {
					if (ConstantArray *CA = dyn_cast<ConstantArray>(switch_arr->getOperand(0))) {
						// based on SimplifyCFG SwitchLookupTable::SwitchLookupTable
						size_t elmCnt = CA->getType()->getNumElements();
						if (elmCnt != (1llu << indexWidth)) {
							// dbgs() << "not enough items (" << elmCnt << ") for " << indexWidth << "b index\n";
							// the table is not completely filled
							continue;
						}
						romData.reserve(elmCnt);
						for (APInt i(indexWidth, 0);; ++i) {
							uint64_t srcIndex = (i - indexOff).getZExtValue();
							auto *item = CA->getAggregateElement(srcIndex);
							romData.push_back(item);
							if (i == elmCnt - 1)
								break;
						}
						IRBuilder<> builder(&I);
						Value *newGep = cteateGEPtoGlobalData(builder, BB, switch_tableidx, romData);
						I.replaceAllUsesWith(newGep);
					}
				}
			}
		} else {
			// search for pattern like:
			//
			//  %switch.tableidx = sub i4 %i0, -8
			//  %switch.cast = zext i4 %switch.tableidx to i48
			//  %switch.shiftamt = mul i48 %switch.cast, 3
			//  %switch.downshift = lshr i48 115535837505169, %switch.shiftamt
			//  %switch.masked = trunc i48 %switch.downshift to i3
			uint64_t elementWidth;
			ConstantInt *indexOff;
			ConstantInt *romBitVec;
			if (match(&I,
			/*masked*/m_Trunc(
			/*downshift*/m_LShr(m_ConstantInt(romBitVec),
			/*shiftamt*/m_Mul(
			/*cast*/m_ZExt(
			/*tableidx*/m_Sub(m_Value(switch_tableidx), m_ConstantInt(indexOff))), m_ConstantInt(elementWidth)))))
					&& I.getType()->getIntegerBitWidth() == elementWidth) {
				//dbgs() << "table shift detected\n";
				size_t romBitVecWidth = romBitVec->getType()->getIntegerBitWidth();
				size_t elementCnt = romBitVecWidth / elementWidth;
				assert((elementWidth % elementWidth) == 0);

				auto *elmT = Type::getIntNTy(BB.getContext(), elementWidth);
				romData.resize(elementCnt);
				std::fill(romData.begin(), romData.end(), nullptr);
				auto bv = romBitVec->getValue();
				for (size_t i = 0; i < elementCnt; ++i) {
					auto *C = ConstantInt::get(elmT, bv.trunc(elementWidth));
					uint64_t dstIndex = (i + indexOff->getValue()).getZExtValue();
					romData[dstIndex] = C;
					bv.lshrInPlace(elementWidth);
				}
				for (auto item : romData) {
					assert(item != nullptr);
				}
				IRBuilder<> builder(&I);
				Value *newGep = cteateGEPtoGlobalData(builder, BB, switch_tableidx, romData);
				Value * newLoad = builder.CreateLoad(elmT, newGep, true, "switch.table.val");
				I.replaceAllUsesWith(newLoad);

			} else {
				switch_tableidx = nullptr;
			}
		}
	}
	return changed;
}

}
