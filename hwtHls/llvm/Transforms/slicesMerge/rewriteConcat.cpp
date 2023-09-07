#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewritePhiShift.h>

using namespace llvm;

namespace hwtHls {

/*
 * :note: end will point at newly added member with new PHINode
 * */
void mergePhisInConcatMemberVector(SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin, SmallVector<OffsetWidthValue>::iterator &end,
		Instruction *userToSkip, const CreateBitRangeGetFn &createSlice, DceWorklist &dce) {
	std::vector<PHINode*> phis;
	phis.reserve(end - begin);

	for (auto _phi = begin; _phi != end; ++_phi) {
		PHINode *phi = dyn_cast<PHINode>(_phi->value);
		assert(phi);
		assert(_phi->offset == 0);
		auto width = phi->getType()->getIntegerBitWidth();
		assert(_phi->width == width);
		phis.push_back(phi);
	}
	auto widerPhi = mergePhisToWiderPhi(members[0].value->getContext(), "concatPhi", phis);
	size_t offset = 0;
	for (auto _phi = begin; _phi != end; ++_phi) {
		for (auto U : _phi->value->users()) {
			if (U != userToSkip) { // replace PHI with slice of the PHI if needed
				auto I = dyn_cast<Instruction>(_phi->value);
				IRBuilder<> builder(I);
				IRBuilder_setInsertPointBehindPhi(builder, I);
				auto *slice = createSlice(&builder, widerPhi, offset, _phi->width);
				I->replaceAllUsesWith(slice);
				dce.insert(*I);
				break;
			}
		}
		offset += _phi->width;
	}

	--end; // keep item with last phi for a new phi
	members.erase(begin, end);
	begin->value = widerPhi;
	begin->offset = 0;
	begin->width = widerPhi->getType()->getIntegerBitWidth();
	end = begin + 1; // set current end to a member behind newly added member
}

bool rewriteConcat(CallInst *I, const CreateBitRangeGetFn &createSlice, DceWorklist &dce, llvm::Value **_newI) {
	IRBuilder<> builder(I);
	ConcatMemberVector values(builder, nullptr);

	for (auto &A : I->args()) {
		values.push_back(OffsetWidthValue::fromValue(A.get()));
	}
	bool modified = false;
	auto &members = values.members;
	auto phiMembersBegin = members.end();
	for (auto m = members.begin(); m != members.end(); ++m) {
		PHINode *phi = nullptr;
		if (m->offset == 0 && m->width == m->value->getType()->getIntegerBitWidth()) {
			phi = dyn_cast<PHINode>(m->value);
			if (phi) {
				if (phiMembersBegin == members.end()) {
					phiMembersBegin = m;
					continue;
				} else if (dyn_cast<PHINode>(phiMembersBegin->value)->getParent() == phi->getParent()) {
					continue;
				}
			}
		}
		// end of compatible PHI sequence detected
		if (phiMembersBegin != members.end() && (m - phiMembersBegin) > 1) {
			// merge PHIs in range <phiMembersBegin, m) to a single PHI and replace them in members vector
			mergePhisInConcatMemberVector(members, phiMembersBegin, m, I, createSlice, dce);
			modified = true;
		}
		if (phi) {
			phiMembersBegin = m;
		} else {
			phiMembersBegin = members.end();
		}
	}
	if (phiMembersBegin != members.end() && (members.end() - phiMembersBegin) > 1) {
		// merge PHIs in range <phiMembersBegin, m) to a single PHI and replace them in members vector
		auto end = members.end();
		mergePhisInConcatMemberVector(members, phiMembersBegin, end, I, createSlice, dce);
		modified = true;
	}

	// the Concat can have only operands modified and rewrite may not be required
	if (values.members.size() != I->getNumOperands() - 1) { // 1 for function def.
		assert(values.members.size() < I->getNumOperands() - 1);
		auto newI = values.resolveValue(I);
		if (_newI)
			*_newI = newI;
		assert(newI != I);
		I->replaceAllUsesWith(newI);
		dce.insert(*I);
		modified = true;
	}

	return modified;
}

}
