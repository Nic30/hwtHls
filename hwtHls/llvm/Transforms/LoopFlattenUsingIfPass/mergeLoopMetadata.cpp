#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass/mergeLoopMetadata.h>

#include <llvm/Transforms/Utils/LoopUtils.h>

#include <hwtHls/llvm/Transforms/utils/loopHwtHlsMetadata.h>

using namespace llvm;

namespace hwtHls {
const std::string LoopFlattenUsingIfPass_followup =
		"hwthls.loop.flattenusingif.followup";

void mergeLlvmLoopMd(llvm::Loop &SrcL, llvm::Loop &DstL) {
	MDNode *llvmLoopMdSrcOriginal = Loop_getHwtHlsLoopID(SrcL);
	assert(llvmLoopMdSrcOriginal);
	std::optional<MDNode*> llvmLoopMdSrcFollowup = makeFollowupLoopID(
			llvmLoopMdSrcOriginal, { LoopFlattenUsingIfPass_followup });
	if (llvmLoopMdSrcFollowup.has_value() && llvmLoopMdSrcFollowup.value()) {
		MDNode *llvmLoopMdSrc = llvmLoopMdSrcFollowup.value();
		MDNode *llvmLoopMdDst = Loop_getHwtHlsLoopID(DstL);
		llvm::MDNode *res = nullptr;
		std::vector<llvm::Metadata*> MDs_tmp;
		std::set<std::string> parentKeyValues;
		if (llvmLoopMdDst) {
			// llvm::MDNode::getTemporary(Context, {}).get()
			MDs_tmp.push_back(nullptr);
			bool first = true;
			for (auto &curOp : llvmLoopMdDst->operands()) {
				if (first) {
					assert(curOp.get() == llvmLoopMdDst);
					first = false;
				} else {
					MDs_tmp.push_back(curOp.get());
					MDNode *MD = dyn_cast<MDNode>(curOp.get());
					if (MD && MD->getNumOperands() >= 1) {
						if (MDString *S = dyn_cast<MDString>(
								MD->getOperand(0))) {
							parentKeyValues.insert(S->getString().str());
						}
					}
				}
			}
		}
		bool first = true;
		for (auto &srcOp : llvmLoopMdSrc->operands()) {
			// expects tuples (keyStr, value)
			// based on llvm::findOptionMDForLoopID
			if (first) {
				first = false;
				continue;
			}
			// Iterate over the metdata node operands and look for MDString metadata.
			MDNode *MD = dyn_cast<MDNode>(srcOp.get());
			if (MD && MD->getNumOperands() >= 1) {
				if (MDString *S = dyn_cast<MDString>(MD->getOperand(0))) {
					// MDString holding name from excludeKeys.
					if (parentKeyValues.contains(S->getString().str()))
						continue;
				}
			}
			MDs_tmp.push_back(MD);
		}

		res = llvm::MDNode::get(llvmLoopMdSrc->getContext(), MDs_tmp);
		res->replaceOperandWith(0, res);
		Loop_setHwtHlsLoopID(DstL, res);
	}
	Loop_setHwtHlsLoopID(SrcL, nullptr);
}

}
