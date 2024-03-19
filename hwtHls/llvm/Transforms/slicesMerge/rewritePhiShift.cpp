#include <hwtHls/llvm/Transforms/slicesMerge/rewritePhiShift.h>

#include <map>
#include <sstream>

#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/SetVector.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/slicesMerge/utils.h>

using namespace llvm;
using namespace std;

namespace hwtHls {

void collectAllChanedPhisInBlock(PHINode &I, map<PHINode*, shared_ptr<set<PHINode*>>> &phiGroups) {
	shared_ptr<set<PHINode*>> iPhiGroup = nullptr;
	auto _iGroup = phiGroups.find(&I);
	if (_iGroup != phiGroups.end())
		iPhiGroup = _iGroup->second;

	for (auto *O : I.operand_values()) {
		if (auto parentPhi = dyn_cast<PHINode>(O)) {
			if (parentPhi->getParent() != I.getParent()) {
				continue;
			}
			shared_ptr<set<PHINode*>> parentGroup = nullptr;
			auto _parentGroup = phiGroups.find(parentPhi);
			if (_parentGroup == phiGroups.end()) {
				// may happen because phi operands can be some PHIs later in this block
				parentGroup = make_shared<set<PHINode*>>();
				parentGroup->insert(parentPhi);
				phiGroups[parentPhi] = parentGroup;
			} else {
				parentGroup = _parentGroup->second;
			}
			if (iPhiGroup == nullptr || iPhiGroup == parentGroup) {
				// assign I to a same group in which parent is
				parentGroup->insert(&I);
				iPhiGroup = parentGroup;
			} else {
				// I is currently in different group than parent, choose larger group and merge smaller group into larger group
				iPhiGroup = mergeGroups<PHINode*>(phiGroups, iPhiGroup, parentGroup);
			}
		}
	}
	if (iPhiGroup == nullptr) {
		iPhiGroup = make_shared<set<PHINode*>>();
		iPhiGroup->insert(&I);
	}
	phiGroups[&I] = move(iPhiGroup);
}
vector<PHINode*> sortPhiGroup(BasicBlock &BB, set<PHINode*> &group) {
	vector<PHINode*> res;
	for (auto &phi : BB.phis()) {
		if (res.size() == group.size())
			return res;
		if (group.find(&phi) != group.end())
			res.push_back(&phi);
	}
	assert(res.size() == group.size());
	return res;
}

PHINode* mergePhisToWiderPhi(LLVMContext & C, const Twine& nameStem, const std::vector<PHINode*> & phis) {
	size_t resWidth = 0;
	//stringstream _name;
	//_name << nameStem << "<";
	int valCnt = -1;
	for (auto _phi : phis) {
		resWidth += _phi->getType()->getIntegerBitWidth();
		//auto _phiName = _phi->getName().str();
		//for (auto recognizedName: {"concatPhi<", "shiftPhi<"})
		//	if (_phiName.rfind(recognizedName, 0) == 0 && _phiName.back() == '>') {
		//		_phiName = std::string(_phiName.begin()+strlen(recognizedName), _phiName.end()-1);
		//	}
		//_name << _phiName << ",";

		if (valCnt == -1) {
			valCnt = _phi->getNumIncomingValues();
		} else {
			assert((unsigned )valCnt == _phi->getNumIncomingValues());
		}
	}
	//_name << ">";
	IRBuilder<> builder(phis.back());
	auto lastPhiIt = builder.GetInsertPoint();
	builder.SetInsertPoint(&*++lastPhiIt);

	auto name = nameStem;  //_name.str();
	auto *resTy = Type::getIntNTy(C, resWidth);
	PHINode *widerPhi = builder.CreatePHI(resTy, phis[0]->getNumIncomingValues(), name);

	// for each predecessor block construct a concatenation of incomming values
	for (size_t i = 0; i < (unsigned) valCnt; ++i) {
		BasicBlock *srcBB = nullptr;
		ConcatMemberVector values(builder, nullptr);
		for (auto _phi : phis) {
			Value *v;
			if (srcBB == nullptr) {
				srcBB = _phi->getIncomingBlock(i);
				v = _phi->getIncomingValue(i);
			} else {
				auto _srcBB = _phi->getIncomingBlock(i);
				if (_srcBB == srcBB) {
					v = _phi->getIncomingValue(i);
				} else {
					// case where this phi does not have same order of block in operands
					v = _phi->getIncomingValueForBlock(srcBB);
				}
			}
			values.push_back(OffsetWidthValue::fromValue(v));
		}
		// insert before terminator
		auto srcBBEndIt = srcBB->end();
		--srcBBEndIt;
		auto srcVal = values.resolveValue(&*srcBBEndIt);
		widerPhi->addIncoming(srcVal, srcBB);
	}
	return widerPhi;
}

bool phiShiftPatternRewrite(BasicBlock &BB, const CreateBitRangeGetFn & createSlice, DceWorklist & dce) {
	map<PHINode*, shared_ptr<set<PHINode*>>> phiGroups;
	for (auto &phi : BB.phis()) {
		collectAllChanedPhisInBlock(phi, phiGroups);
	}
	SetVector<PHINode*> toRm;
	for (auto &phi : BB.phis()) {
		if (toRm.count(&phi))
			continue; // already converted PHI

		auto group = phiGroups.find(&phi);
		if (group == phiGroups.end())
			continue; // just create new PHI
		if (group->second->size() == 1)
			continue; // pointless to rewrite to same

		auto phigroup = sortPhiGroup(BB, *group->second);
		toRm.insert(phigroup.begin(), phigroup.end());
		auto widerPhi = mergePhisToWiderPhi(BB.getContext(), "shiftPhi", phigroup);
		IRBuilder<> builder(&*BB.begin());
		IRBuilder_setInsertPointBehindPhi(builder, &*BB.begin());
		size_t lowBitNo = 0;
		for (auto _phi : phigroup) {
			size_t bitWidth = _phi->getType()->getIntegerBitWidth();
			auto phiSlice = createSlice(&builder, widerPhi, lowBitNo, bitWidth);
			dce.updateSlicesBeforeReplace(*_phi, *phiSlice);
			_phi->replaceAllUsesWith(phiSlice);
			lowBitNo += bitWidth;
		}
	}
	for (auto phi : toRm) {
		for (Use& v: phi->incoming_values())
			if (auto ii = dyn_cast<Instruction>(v.get()))
				dce.insert(*ii);
		phi->eraseFromParent();
	}
	return toRm.size() != 0;
}

}

