#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB.h>

#include <map>
#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/ErrorHandling.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/utils/cfgUtils.h>

using namespace llvm;

namespace hwtHls {

void demoteReg2MemForPhisWithExtraOperands(
	IRBuilderBase &Builder, BasicBlock &BB,
	SmallVector<AllocaInst *> &tmpAllocas) {
	auto *entryEnd = BB.getParent()->getEntryBlock().getTerminator();
	for (auto &phi : make_early_inc_range(BB.phis())) {
		// perform reg2mem for phi which now have extra incomming
		// values for predecessors which were rerouted
		Builder.SetInsertPoint(entryEnd);
		auto tmpAlloca = Builder.CreateAlloca(phi.getType());
		tmpAlloca->takeName(&phi);
		tmpAllocas.push_back(tmpAlloca);
		// store to alloca in predecessor
		for (const auto &[pred, Val] :
			 zip(phi.blocks(), phi.incoming_values())) {
			Builder.SetInsertPoint(pred->getTerminator());
			Builder.CreateStore(Val, tmpAlloca);
		}
		std::map<BasicBlock *, LoadInst *> loadPerBBCache;
		SmallVector<User *> phiUsers(phi.users());
		for (auto *u : phiUsers) {
			auto ui = dyn_cast<Instruction>(u);
			assert(ui);
			auto bbForLd = ui->getParent();
			if (auto uPhi = dyn_cast<PHINode>(ui)) {
				// for phi we need to probe all operands and the
				// value load must be constructed in predecessor
				// block
				for (const auto &[pred, v] :
					 zip(uPhi->blocks(), uPhi->incoming_values())) {
					LoadInst *ld;
					if (v == &phi) {
						auto existingLd = loadPerBBCache.find(bbForLd);
						if (existingLd != loadPerBBCache.end()) {
							ld = existingLd->second;
						} else {
							Builder.SetInsertPoint(pred->getTerminator());
							ld = Builder.CreateLoad(phi.getType(), tmpAlloca);
							loadPerBBCache[bbForLd] = ld;
						}
						uPhi->setIncomingValueForBlock(pred, ld);
					}
				}
			} else {
				// for normal instructions the load must dominate
				// user instruction
				LoadInst *ld;
				auto existingLd = loadPerBBCache.find(bbForLd);
				if (existingLd != loadPerBBCache.end()) {
					// optionally move load of tmp alloca more up to
					// dominate this use
					ld = existingLd->second;
					if (ui->comesBefore(ld)) {
						ld->moveBefore(ui->getIterator());
					}
				} else {
					Builder.SetInsertPoint(ui);
					ld = Builder.CreateLoad(phi.getType(), tmpAlloca);
					loadPerBBCache[bbForLd] = ld;
				}
				ui->replaceUsesOfWith(&phi, ld);
			}
		}
		phi.eraseFromParent();
	}
}

bool HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB(
	llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
	llvm::BasicBlock &BB, bool &exprChanged) {
	auto term = BB.getTerminator();
	if (!all_of(BB, [](Instruction &I) {
			return isa<PHINode>(&I) || I.isTerminator();
		})) {
		return false;
	}
	if (DTU.hasPendingUpdates())
		DTU.flush();
	auto &DT = DTU.getDomTree();
	if (any_of(predecessors(&BB), [&BB, &DT](BasicBlock *predBB) {
			return DT.dominates(&BB, predBB);
		})) {
		return false; // can not unswitch loop header
	}
	// if the branch is driven from the phi with constant operands
	// we can directly jump from predecessor to successor without visiting this
	// block. however we must update uses of values defined in this
	if (auto br = dyn_cast<BranchInst>(term)) {
		auto c = br->getCondition();
		auto cPhi = dyn_cast<PHINode>(c);
		if (!cPhi)
			return false;
		if (cPhi->getParent() !=
			&BB) // if branch condition is not phi of the same block
			return false;

		// for predecessors check if branch value is constant
		// and if this is the case transplant branch from BB to a branch
		// directly from pred
		bool mustRegeneratePhis = false;
		for (const auto &[pred, c] :
			 zip(cPhi->blocks(), cPhi->incoming_values())) {
			if (auto cConst = dyn_cast<ConstantInt>(c)) {
				BasicBlock *newSuc;
				if (cConst->getZExtValue()) {
					newSuc = br->getSuccessor(0);
				} else {
					newSuc = br->getSuccessor(1);
				}
				if (newSuc == &BB) {
					continue; // can not unswitch backedge of the loop
				}
				if (is_contained(successors(pred), newSuc)) {
					llvm_unreachable(
						"[todo] create a new block so phis can distinguish "
						"which path was taken if phi values differ");
				}
				assert(newSuc != &BB);
				pred->getTerminator()->replaceSuccessorWith(&BB, newSuc);
				DTU.applyUpdates({
					{DominatorTree::Delete, pred, &BB},
					{DominatorTree::Insert, pred, newSuc},
				});

				for (auto &newSucPhi : newSuc->phis()) {
					auto vForBB = newSucPhi.getIncomingValueForBlock(&BB);
					auto newV = vForBB;
					auto vForBbAsI = dyn_cast<Instruction>(vForBB);
					if (vForBbAsI && vForBbAsI->getParent() == &BB) {
						auto bbPhi = dyn_cast<PHINode>(vForBbAsI);
						assert(bbPhi && "BB is expected to contain only PHIs "
										"and terminator");
						newV = bbPhi->getIncomingValueForBlock(pred);
					}
					newSucPhi.addIncoming(newV, pred);
				}
				// :attention: now the uses of PHIs from BB are potentially not
				// dominated by the definition in BB
				//   because new path directly from pred was added, we fit this
				//   at the end after predecessors are processed
				mustRegeneratePhis = true;
			}
		}
		
		if (mustRegeneratePhis) {
			SmallVector<AllocaInst *> tmpAllocas;
			demoteReg2MemForPhisWithExtraOperands(Builder, BB, tmpAllocas);
			if (DTU.hasPendingUpdates())
				DTU.flush();
			auto &DT = DTU.getDomTree();
			llvm::PromoteMemToReg(tmpAllocas, DT);
			return true;
		}
	}
	//  else if (auto sw = dyn_cast<SwitchInst>(term)) {
	// 	auto c = br->getCondition();
	// 	auto cPhi = dyn_cast<PHINode>(c);
	// 	if (!cPhi)
	// 		return false;
	// 	if (cPhi->getParent() != &BB)
	// 		return false;
	// 	for (const auto &[pred, c] :
	// 		 zip(cPhi->blocks(), cPhi->incoming_values())) {
	// 		if (auto cConst = dyn_cast<ConstantInt>(c)) {
	// 			llvm_unreachable("[todo]");
	// 		}
	// 	}
	// }
	return false;
}

} // namespace hwtHls