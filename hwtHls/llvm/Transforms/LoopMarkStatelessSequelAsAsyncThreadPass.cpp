#include <hwtHls/llvm/Transforms/LoopMarkStatelessSequelAsAsyncThreadPass.h>

#include <unordered_set>

#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/LoopPass.h>
#include <llvm/Analysis/MemorySSA.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CFG.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>

#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/liveness.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/threadSplit.h>
#include <hwtHls/llvm/Transforms/utils/loopHwtHlsMetadata.h>

using namespace llvm;

#define DEBUG_TYPE "loop-mark-stateless-sequel"
// #define DEBUG_DUMP_CFG_AFTER_EACH_STEP
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(x) x

namespace hwtHls {

const std::string LoopMarkStatelessSequelAsAsyncThreadPass::METADATA_NAME = "hwthls.loop.mark_stateless_sequel";
const std::string LoopMarkStatelessSequelAsAsyncThreadPass::METADATA_NAME_followup = LoopMarkStatelessSequelAsAsyncThreadPass::METADATA_NAME + ".followup";
	
// instruction is modifying state if it drives the header PHI operand
// or branch which have effect on header PHI operands
// or if it io for memory which have both store and load instructions in this
// loop or if there are other instructions for this io in the code outside of
// this loop or if not all io instructions for this io can be extracted
void findInstrModifyingState(
	llvm::LoopInfo &LI, Loop &L,
	ArrayRef<Instruction *> knownStateModifyingInstr,
	std::unordered_set<Instruction *> &stateModifyingInstr) {

	SmallVector<Instruction *> worklist;
	SmallVector<Instruction *> cfgWorklist;
	worklist.append(knownStateModifyingInstr.begin(),
					knownStateModifyingInstr.end());
	for (auto &phi : L.getHeader()->phis()) {
		worklist.push_back(&phi);
	}
	for (auto *BB : L.blocks()) {
		auto T = BB->getTerminator();
		if (auto Br = dyn_cast<BranchInst>(T)) {
			if (!Br->isConditional())
				continue;
		}
		worklist.push_back(T);
	}
	// use->def search
	while (!worklist.empty()) {
		auto *I = worklist.pop_back_val();
		if (!stateModifyingInstr.insert(I).second)
			continue;
		for (auto *O : I->operand_values()) {
			if (auto UI = dyn_cast<Instruction>(O)) {
				if (!L.contains(UI))
					continue;
				worklist.push_back(UI);
			}
		}
	}
}

/*
 * Insert common proxy block on given edges so all edges will pass trough this new proxy block.
 * Functionality is similar to llvm ControlFlowUtils.h/ControlFlowHub
 * 
 * .. code-block::
 *     ; input:
 *     bb1:
 *       br label %bb2
 *     bb3:
 *       br i1 %c, label %bb3.t, label %bb3.f
 *     bb4:
 *       switch i16 %c2, label %bb4.def [
 *        i16 0, label %bb4.case0
 *        i16 1, label %bb4.case1
 *       ]
 *     
 *     ; edges = =[(%bb1, %bb2), (%bb3, %bb3.t), (%bb3, %bb3.f),
 *     ;          (%bb4, %bb4.def), (%bb4, %bb4.case0), (%bb4, %bb4.case1)]
 *     
 *     ; output: 
 *     bb1:
 *       br label %bb.proxy
 *     bb3:
 *       br i1 %c, label %bb.proxy, label %bb3.0
 *     bb3.0: ; generated to have unique pred for phi
 *       br label %bb.proxy
 *     bb4:
 *       switch i16 %c2, label %bb.proxy [
 *        i16 0, label %bb4.0
 *        i16 1, label %bb4.1
 *       ]
 *     bb4.0:
 *       br label %bb.proxy
 *     bb4.1:
 *       br label %bb.proxy
 *     
 *     ; PHI to resolve jump src and switch inst to implement jump as it was in original edge.
 *     bb.proxy:
 *       %proxySrc = phi i64 [0, %bb1], [1, %bb3], [2, %bb3.0], [3, %bb4], [5, %bb4.0], [6, %bb4.1]
 *       switch i64 %proxySrc, label %bb.proxy.def [
 *        i64 0, label %bb2
 *        i64 1, label %bb3.t
 *        i64 2, label %bb3.f
 *        i64 3, label %bb4.def
 *        i64 4, label %bb4.case0
 *        i64 5, label %bb4.case1
 *       ]
 *     bb.proxy.def:
 *       unreachable
 */
using BasicBlockEdge = Loop::Edge;
BasicBlock *insertProxyBlockInLoop(const SmallVector<BasicBlockEdge> &edges,
							 DomTreeUpdater &DTU, LoopInfo &LI, Loop &L,
							 MemorySSAUpdater *MSSAU, 
							 std::vector<llvm::AllocaInst*>& tmpAllocas) {
	assert(!MSSAU && "NotImplemented");
	// :note: edges must be unique
	if (edges.empty())
		return nullptr;

	Function &F = *edges[0].first->getParent();
	LLVMContext &Ctx = F.getContext();
	
	if (DTU.hasPendingUpdates())
		DTU.flush();
	
	std::map<BasicBlock *, SetVector<Instruction *>> allLiveins =
		computeAllLiveins(F, DTU.getDomTree());
	// demote livein of dst blocks to Alloca if
	// def does not dominate all dst blocks
	{ 
		std::unordered_set<Value*> resolved;
		auto headerIP = L.getHeader()->getFirstInsertionPt();
		for (const auto & [_, dstBB]: edges) {
			if (resolved.contains(dstBB))
				continue;
			auto dstBBLiveins = allLiveins.find(dstBB);
			assert(dstBBLiveins != allLiveins.end());
			for (auto *liveinInst: dstBBLiveins->second) {
				auto a = DemoteRegToStack(*liveinInst, false, headerIP);
				tmpAllocas.push_back(a);
			}
		}
	}
	BasicBlock *proxyBB = BasicBlock::Create(Ctx, "bb.proxy", &F);
	BasicBlock *proxyDefBB = BasicBlock::Create(Ctx, "bb.proxy.def", &F);
	new UnreachableInst(Ctx, proxyDefBB);

	// Map original edges to unique IDs
	DenseMap<BasicBlockEdge, unsigned> edgeIDs;
	for (unsigned i = 0; i < edges.size(); ++i) {
		edgeIDs[edges[i]] = i;
	}

	// :note: proxySrcId holds the id of edge which enters the proxy
	//        so later the proxy returns with proper jump
	//        to where this jump was originally jumping before this proxy
	//        was inserted on this edge
	Type *IDType = Type::getIntNTy(Ctx, log2ceil(edges.size()));
	PHINode *proxySrcId = PHINode::Create(IDType, edges.size(), "proxySrc",
										proxyBB->getFirstInsertionPt());
	SwitchInst *proxySwitch =
		SwitchInst::Create(proxySrcId, proxyDefBB, edges.size(), proxyBB);
	DTU.applyUpdates({{DominatorTree::Insert, proxyBB, proxyDefBB}});
	L.addBasicBlockToLoop(proxyBB, LI);

	SmallPtrSet<BasicBlock *, 32> seenSrcBlocks;
	DenseMap<BasicBlockEdge, BasicBlock *> tmpDstBlocks;
	for (const auto &edge : edges) {
		const auto &[srcBB, dstBB] = edge;
		unsigned id = edgeIDs[edge];
		BasicBlock *pred;
		if (seenSrcBlocks.contains(srcBB)) {
			// because there is a collision
			auto tmpBB = BasicBlock::Create(Ctx, srcBB->getName() + ".slseq.PEntry", &F);
			tmpDstBlocks[{srcBB, dstBB}] = tmpBB;
			BranchInst::Create(proxyBB, tmpBB); // :note: tmpBB br -> proxyBB
			srcBB->getTerminator()->replaceSuccessorWith(dstBB, tmpBB);
			DTU.applyUpdates({{DominatorTree::Delete, srcBB, dstBB},
							  {DominatorTree::Insert, srcBB, tmpBB},
							  {DominatorTree::Insert, tmpBB, proxyBB}});
			pred = tmpBB;
			L.addBasicBlockToLoop(tmpBB, LI);
		} else {
			srcBB->getTerminator()->replaceSuccessorWith(dstBB, proxyBB);
			DTU.applyUpdates({{DominatorTree::Delete, srcBB, dstBB},
							  {DominatorTree::Insert, srcBB, proxyBB}});
			seenSrcBlocks.insert(srcBB);
			pred = srcBB;
		}
		ConstantInt *idC = dyn_cast<ConstantInt>(ConstantInt::get(IDType, id));
		proxySrcId->addIncoming(idC, pred);

		auto* srcTerm = srcBB->getTerminator();
		if (srcTerm->hasMetadata() || !dstBB->phis().empty()) {
			// must insert a new tmp block with new terminator to accommodate metadata
			// because we may have just converted latch/exit to block somewhere
			// inside of the loop so for example Loop metadata would be lost
			// or we need to block for phis in dstBB 
			
			auto tmpDstBB = BasicBlock::Create(Ctx, srcBB->getName() + ".slseqPExit", &F);
			if (Loop* dstL = LI.getLoopFor(dstBB))  {
				dstL->addBasicBlockToLoop(tmpDstBB, LI);
			}
			auto Br = BranchInst::Create(dstBB, tmpDstBB); // :note: tmpDstBB br -> dstBB
			Br->copyMetadata(*srcTerm);
			srcTerm->eraseMetadataIf([](unsigned int, MDNode *) { return true;});
			DTU.applyUpdates({{DominatorTree::Insert, tmpDstBB, dstBB}});
			proxySwitch->addCase(idC, tmpDstBB);
			dstBB->replacePhiUsesWith(srcBB, tmpDstBB);
		} else {
			proxySwitch->addCase(idC, dstBB);
		}
		DTU.applyUpdates({{DominatorTree::Insert, proxyBB, dstBB}});
	}
	return proxyBB;
}

// Remove instructions which are driving only llvm.assume() (+ assume itself)
// in extracted region, if llvm.assume() has no transitive input which will
// is used by something else in extracted region.
void prunePureAssumeFanOutConesFromCompatibleInstr(llvm::SetVector<llvm::Instruction *> &selectedInstr) {
    // Collect primary outputs (instructions that have no use and are not llvm.assume calls)
    SetVector<Instruction *> primaryOutputs;
    bool anyAssumeSeen = false;
    for (auto *I : selectedInstr) {
		if (isa<AssumeInst>(I)) {
			anyAssumeSeen = true;			
            continue;
		}
		
        // Search for instructions with no uses
		// (excluding assumes which were handled above)
        bool hasUsesInRegion = false;
        for (auto *U : I->users()) {
            if (auto *UI = dyn_cast<Instruction>(U)) {
                if (selectedInstr.count(UI)) {
                    hasUsesInRegion = true;
                    break;
                }
            }
        }
        
        if (!hasUsesInRegion) {
            primaryOutputs.insert(I);
        }
    }
	if (!anyAssumeSeen) 
		// no need to filter
		return;
    
    // Walk and collect in use->def direction from all primary outputs
    // (transitive inputs feeding into primary outputs)
    SetVector<Instruction *> transitiveInputs;
    std::vector<Instruction *> worklist(primaryOutputs.begin(), primaryOutputs.end());
    
    while (!worklist.empty()) {
        auto *I = worklist.back();
        worklist.pop_back();
        
        // Collect all defs feeding into this instruction (within selectedInstr)
        for (Value *op : I->operand_values()) {
            if (auto *defInst = dyn_cast<Instruction>(op)) {
                if (selectedInstr.contains(defInst) && transitiveInputs.insert(defInst)) {
                    worklist.push_back(defInst);
                }
            }
        }
    }
    
    // Walk and collect in def->use direction from all collected instructions
    // (complete fan-out cones from transitive inputs)
    SetVector<Instruction *> newSelectedInstr;
    newSelectedInstr.insert(primaryOutputs.begin(), primaryOutputs.end());
    newSelectedInstr.insert(transitiveInputs.begin(), transitiveInputs.end());
    
    worklist.assign(transitiveInputs.begin(), transitiveInputs.end());
    
    while (!worklist.empty()) {
        Instruction *inst = worklist.back();
        worklist.pop_back();
        
        // Collect all uses of this instruction (within selectedInstr)
        for (auto *U : inst->users()) {
            if (Instruction *UI = dyn_cast<Instruction>(U)) {
                if (selectedInstr.count(UI) && newSelectedInstr.insert(UI)) {
                    worklist.push_back(UI);
                }
            }
        }
    }
    
    // Remove instructions which were not visited from selectedInstr
	selectedInstr = newSelectedInstr;
}

bool LoopMarkStatelessSequelAsAsyncThreadPass::findCompatibleInstructions(
	llvm::LoopInfo &LI, llvm::Loop &L,
	std::unordered_set<Instruction *> &incompatible,
	SetVector<Instruction *> &compatible) {

	SetVector<Instruction *> explicitlyIncompatible;
	DenseMap<Value *, bool> IOcompatibility;
	// first check which IOs are touched by prequel section
	for (;;) {
		findInstrModifyingState(LI, L, explicitlyIncompatible.getArrayRef(),
								incompatible);
		// errs() << "incompatible:\n";
		// for (auto *I : incompatible) {
		// 	errs() << "  " << *I << "\n";
		// }

		auto incompatibleSize = incompatible.size();
		// findIncopatibleIoInstr(LI, L, compatible, incompatible,
		// 					   IOcompatibility);
		auto isSelectedFn = [&L, &incompatible](Instruction &I) {
			return L.contains(&I) && !incompatible.contains(&I);
		};
		//checkIoIsPrivateToSelectedRegion(LI, L, *L.getHeader(), isSelectedFn,
		//								 IOcompatibility);

		auto collectIoUses = [&IOcompatibility, &isSelectedFn](Instruction &I) {
			Value *io;
			if (auto ld = dyn_cast<LoadInst>(&I)) {
				io = ld->getPointerOperand();
			} else if (auto st = dyn_cast<StoreInst>(&I)) {
				io = st->getPointerOperand();
			} else {
				return;
			}
        
			io = findIoDef(io);
			if (IOcompatibility.contains(io)) {
				return;
			}
			bool isCompatible =
				allLoadStoreInstrAreCompatible(io, isSelectedFn);
			IOcompatibility.insert({io, isCompatible});
		};
		for (auto *BB : L.blocks()) {
			for (auto &I : *BB) {
				collectIoUses(I);
			}
		}

		for (const auto &[io, isCompatible] : IOcompatibility) {
			if (!isCompatible) {
				walkAllUserGepLoadStoreInstructions(
					io, [&incompatible](Instruction &I) {
						incompatible.insert(&I);
					});
			}
		}
		bool allCompatibleAreTerminators = true;
		for (BasicBlock *BB : L.blocks()) {
			for (Instruction &I : *BB) {
				if (!incompatible.contains(&I)) {
					compatible.insert(&I);
					allCompatibleAreTerminators &= I.isTerminator();
				}
			}
		}
		if (compatible.empty() || allCompatibleAreTerminators) {
			return false;
		}

		if (incompatibleSize != incompatible.size()) {
			compatible.clear();
			continue; // some new incompatible instructions were found we have
					  // to construct compatible set again
		}
		break;
	}
	prunePureAssumeFanOutConesFromCompatibleInstr(compatible);
	return true;
}

// DFS use->def mine blocks which will be copied to extract section
void findExtractedRegion(const llvm::Loop &L, 
	const SetVector<Instruction *> &compatibleInstr, 
	const SmallVector<Loop::Edge>& BackedgesAndExitEdges,
	SetVector<BasicBlock*> & extractedRegionBBs) {
	
	auto headerBB = L.getHeader();	
	// if block has any compatible instruction then is considered part of region
	SmallVector<BasicBlock*> worklist;
	auto addSuccessorsToWorklist = [&L, &extractedRegionBBs, &worklist,
									headerBB](BasicBlock *BB) {
		if (extractedRegionBBs.insert(BB)) {
			for (auto suc : successors(BB)) {
				if (suc == headerBB) {
					continue;
				} else if (!L.contains(BB)) {
					continue;
				} else {
					worklist.push_back(suc);
				}
			}
		}
	};
	
	for (auto *I : compatibleInstr) {
		auto BB = I->getParent();
		addSuccessorsToWorklist(BB);
	}
	// add all trasitive successors of region blocks in loop to region
	// (except for header, it is a special case because region ends on backedge)
	while (!worklist.empty()) {
		auto BB = worklist.pop_back_val();
		addSuccessorsToWorklist(BB);
	}
}

void findExtractedRegionLiveinsNotDominatingRegion(
	Loop &L, DominatorTree &DT,
	const SetVector<BasicBlock *> &extractedRegionBBs,
	const SetVector<Instruction *> &extractedRegionInstrs,
	SetVector<Instruction *> &liveins) {
	assert(!extractedRegionBBs.empty());

	auto onUseSeen = [&L, &DT, &extractedRegionBBs, &extractedRegionInstrs,
					  &liveins](Value *C) {
		if (auto CI = dyn_cast<Instruction>(C)) {
			if (liveins.contains(CI))
				return;

			if (extractedRegionInstrs.contains(CI)) {
				return; // this instruction will move together with blocks
						// and dominance will not change for any user
			}
			if (!L.contains(CI))
				return; // this is guaranteed to dominate whole loop
			bool dominatesAll = true;
			for (auto *rBB : extractedRegionBBs) {
				if (!DT.dominates(CI, rBB)) {
					dominatesAll = false;
					break;
				}
			}
			if (dominatesAll) {
				return;
			} else {
				liveins.insert(CI);
				return;
			}
		}
		return;
	};
	for (auto *BB : extractedRegionBBs) {
		auto T = BB->getTerminator();
		Value *C = nullptr;
		if (auto Br = dyn_cast<BranchInst>(T)) {
			if (Br->isConditional())
				C = Br->getCondition();
		} else if (auto Sw = dyn_cast<SwitchInst>(T)) {
			C = Sw->getCondition();
		} else if (isa<UnreachableInst>(T)) {
			continue;
		}
		if (C)
			onUseSeen(C);
	}
	for (auto *I : extractedRegionInstrs) {
		for (auto U : I->operand_values()) {
			onUseSeen(U);
		}
	}
}

void findRegionEntryEdges(const SetVector<BasicBlock *>& extractedRegionBBs, SmallVector<BasicBlockEdge> & entryEdges) {
	// :attention: assumes that the loop header is not in the extractedRegionBBs
	for (auto * BB: extractedRegionBBs) {
		for (auto pred: predecessors(BB)) {
			if (!extractedRegionBBs.contains(pred))
				entryEdges.push_back({pred, BB});
		}
	}
}

void moveExtractedInstructions(
	BasicBlock &BBsrc, BasicBlock &BBdst,
	const DenseMap<Value *, Value *> &toNewValMap,
	const SetVector<Instruction *> &compatibleInstr) {
	for (Instruction &I : make_early_inc_range(BBsrc)) {
		Instruction *newI = nullptr;
		if (I.isTerminator()) {
			newI = I.clone();
		} else if (compatibleInstr.contains(&I)) {
			newI = &I;
			I.removeFromParent();
		}
		if (newI) {
			// update operands
			for (auto &op : newI->operands()) {
				auto opV = op.get();
				auto replacement = toNewValMap.find(opV);
				if (replacement != toNewValMap.end()) {
					op.set(replacement->second);
				}
			}
			newI->insertInto(&BBdst, BBdst.end());
		}
	}
}

void buildJumpsFromProxyBeginToRegionEntryPoints(
	IRBuilderBase &Builder, LoopInfo &LI, DomTreeUpdater &DTU,
	llvm::MemorySSAUpdater *MSSAU, Loop &L,
	BasicBlock *proxyBB, BasicBlock *newExitBB,
	DenseMap<Value *, Value *>& toNewValMap,
	const SetVector<BasicBlock *>& extractedRegionBBs,
	SmallVector<DomTreeUpdater::UpdateT>& DTUpdates) {
	// * The extracted section may have multiple entry points
	//   All enable conditions for them should be known in advance, because
	//   original cfg will still exists before this section
	//   and we are extracting only from section between backedge/exit and
	//   the header or fist child loop
	//   [todo] extract whole child loop if possible

	// * Resolve entry points to extracted region
	auto proxyBBBr = dyn_cast<BranchInst>(proxyBB->getTerminator());
	assert(
		proxyBBBr && !proxyBBBr->isConditional() &&
		proxyBBBr->getSuccessor(0) == newExitBB &&
		"This part of cfg should not been touched from split of the exit");
	auto headerBB = L.getHeader();
	bool headerIsEntrypoint = extractedRegionBBs.contains(headerBB);
	if (headerIsEntrypoint) {
		// there is only a single entry point and that is the loop header
		auto* newEntryBB = static_cast<BasicBlock*>(toNewValMap[headerBB]);
		proxyBBBr->setSuccessor(0, newEntryBB);
		DTUpdates.push_back({DominatorTree::Delete, proxyBB, newExitBB});
		DTUpdates.push_back({DominatorTree::Insert, proxyBB, newEntryBB});
	} else {
		auto &Ctx = proxyBB->getContext();
		auto & F = *proxyBB->getParent();
		// there are potentially multiple entry points,
		// * Prepare Alloca for entryIndex variable, store region entry number to
		//   it on each entry locations in original cfg
		// * read entryIndex in extracted region, and copy cfg of region
		// :note: the proxySrcId in insertProxyBlockInLoop() is holding
		//        value for exit jump from proxy, not the entry jump
		SmallVector<BasicBlockEdge> entryEdges;
		findRegionEntryEdges(extractedRegionBBs, entryEdges);
		Type *entryIdTy = Type::getIntNTy(Ctx, log2ceil(entryEdges.size()));
		Builder.SetInsertPoint(headerBB->getFirstInsertionPt());
		auto entryIdx = Builder.CreateAlloca(entryIdTy, nullptr, "slseq.EntryIdx");
		// initial entryIdx reset
		Builder.CreateStore(PoisonValue::get(entryIdTy), entryIdx);
		SwitchInst * entrySw;
		{
			Builder.SetInsertPoint(proxyBBBr);
			auto entryIdxVal = Builder.CreateLoad(entryIdTy, entryIdx);
			BasicBlock *proxyEntryDefBB = BasicBlock::Create(Ctx, "bb.proxy.entry.def", &F);
			new UnreachableInst(Ctx, proxyEntryDefBB);
			entrySw = Builder.CreateSwitch(entryIdxVal, proxyEntryDefBB);
			proxyBBBr->eraseFromParent();
			proxyBBBr = nullptr;
			DTUpdates.push_back({DominatorTree::Insert, proxyBB, proxyEntryDefBB});
		}
		size_t entryI = 0;
		for (const auto& [srcBB, dstBB]:  entryEdges) {
			ConstantInt* entryIAsV = static_cast<ConstantInt*>(ConstantInt::get(entryIdTy, entryI));
			auto _srcBB = srcBB;
			if (!srcBB->getUniqueSuccessor()) {
				DTU.applyUpdates(DTUpdates);
				DTUpdates.clear();
				_srcBB = SplitEdge(srcBB, dstBB, &DTU.getDomTree(), &LI, MSSAU);
			}
			Builder.SetInsertPoint(_srcBB->getTerminator());
			Builder.CreateStore(entryIAsV, entryIdx);
			auto _newEntryBB = toNewValMap.find(dstBB);
			assert(_newEntryBB != toNewValMap.end());
			auto newEntryBB  = static_cast<BasicBlock*>(_newEntryBB->second);
			
			// update phis of newEntryBB
			if (!newEntryBB->phis().empty()) {
				BasicBlock *tmpEntryBB = nullptr;
				if (is_contained(successors(proxyBB), newEntryBB)) {
					// we need to place extra new block to have unique predecessor for newEntryBB phis
					tmpEntryBB = BasicBlock::Create(Ctx, "bb.proxy.entry." + srcBB->getName(), &F);
					Builder.SetInsertPoint(tmpEntryBB);
					Builder.CreateBr(newEntryBB);
					DTUpdates.push_back({DominatorTree::Insert, tmpEntryBB, newEntryBB});
					L.addBasicBlockToLoop(tmpEntryBB, LI);
				}
				updatePhiNodes(newEntryBB, srcBB, tmpEntryBB ? tmpEntryBB: proxyBB);
				
				if (tmpEntryBB)
					newEntryBB = tmpEntryBB;
			}
			
			entrySw->addCase(entryIAsV, newEntryBB);
			DTUpdates.push_back({DominatorTree::Insert, proxyBB, newEntryBB});
			++entryI;
		}
	}
}

void copyOrMoveRegionBlocks(
	LoopInfo &LI,
	Loop &L,
	BasicBlock *proxyBB, BasicBlock *newExitBB,
	DenseMap<Value *, Value *>& toNewValMap,
	const SetVector<BasicBlock *>& extractedRegionBBs,
	const SetVector<Instruction *>& compatibleInstr,
	SmallVector<DomTreeUpdater::UpdateT>& DTUpdates) {
	// spawn new blocks
	auto & F = *proxyBB->getParent();
	auto & Ctx = proxyBB->getContext();
	for (auto * BB: extractedRegionBBs) {
		BasicBlock *newBB = BasicBlock::Create(Ctx, BB->getName() + ".slseq", &F);
		toNewValMap[BB] = newBB;
	}
	toNewValMap[proxyBB] = newExitBB; // orig code jumped on proxy, new section will jump to end of extracted region
	// move extracted instructions to section proxyBB-newExitBB
	// original code stays as is but extracted instructions are moved or copied to new region
	// which has the same CFG structure as original
	for (BasicBlock * BB: extractedRegionBBs) {
		auto* newBB = static_cast<BasicBlock*>(toNewValMap[BB]);
		moveExtractedInstructions(*BB, *static_cast<BasicBlock*>(newBB), toNewValMap, compatibleInstr);
		assert(newBB->getTerminator());
		DenseSet<BasicBlock*> seenSuc;
				for (auto suc: successors(newBB)) {
			if (seenSuc.insert(suc).second) {
				DTUpdates.push_back({DominatorTree::Insert, newBB, suc});
			}
		}
		L.addBasicBlockToLoop(newBB, LI);
	}
}

bool LoopMarkStatelessSequelAsAsyncThreadPass::processLoop(llvm::LoopInfo &LI, llvm::Loop &L,
											  llvm::DomTreeUpdater &DTU,
											  llvm::MemorySSAUpdater *MSSAU) {
	{
		const MDOperand *AttrMD =
		findStringMetadataForHwtHlsLoop(&L, METADATA_NAME).value_or(nullptr);
		if (!applyOnAll && !AttrMD)
			return false;
	}
	// Save loop properties before it is transformed.
	std::optional<MDNode *> llvmLoopMdFollowup =
		makeFollowupLoopID(L.getLoopID(), {METADATA_NAME_followup});
	L.setLoopID(nullptr); // temporary delete before CFG modifications
	auto returnBackLoopIDMdBeforeExit = [&llvmLoopMdFollowup, &L] {
		if (llvmLoopMdFollowup.has_value())
			// return id back after cfg modifications
			L.setLoopID(llvmLoopMdFollowup.value());
	};
	if (L.getHeader()->phis().empty()) {
		returnBackLoopIDMdBeforeExit();
		return false; // there is no state, everything would be extracted
	}

	SetVector<Instruction *> compatibleInstr;
	{
		std::unordered_set<Instruction *> incompatible;
		if (!findCompatibleInstructions(LI, L, incompatible, compatibleInstr)) {
			returnBackLoopIDMdBeforeExit();
			return false;
		}
	}
	// prepare 1 common block which will be placed in each backedge, and exiting edge
	// * construct phi-switch switch pair to jump to original destination
	SmallVector<Loop::Edge> BackedgesAndExitEdges;
	auto headerBB = L.getHeader();
	for (auto srcBB: predecessors(headerBB)) {
		if (L.contains(srcBB)) {
			BackedgesAndExitEdges.push_back({srcBB, headerBB});
		}
	}
	L.getExitEdges(BackedgesAndExitEdges);

	SetVector<BasicBlock *> extractedRegionBBs;
	findExtractedRegion(L, compatibleInstr, BackedgesAndExitEdges, extractedRegionBBs);
	
	std::vector<llvm::AllocaInst*> tmpAllocas;
	BasicBlock * proxyBB = insertProxyBlockInLoop(BackedgesAndExitEdges, DTU, LI, L, MSSAU, tmpAllocas);
	
	// * prepare section boundaries
	// :note: based on IoLowerAxiMmPass/markReadConsummerSection, LoopMarkStatelessPrequelAsAsyncThreadPass::processLoop
	IRBuilder<> Builder(proxyBB, proxyBB->getFirstInsertionPt());
	ThreadSplitSectionMetadata threadMdObj("slsequel", true, /*beginMayBeAsync*/false, true, true,
										   0, 0);
	auto md = threadMdObj.toMetadata(Builder.getContext());
	CreateThreadSplitBegin(Builder, threadMdObj.name, md);
	auto threadEnd = CreateThreadSplitEnd(Builder, threadMdObj.name, md);
	auto newExitBB = SplitBlock(proxyBB, threadEnd->getIterator(), &DTU, &LI, MSSAU);
	 
	// * Resolve input variables to extracted region
	SetVector<Instruction *> liveins;
	findExtractedRegionLiveinsNotDominatingRegion(
		L, DTU.getDomTree(), extractedRegionBBs, compatibleInstr, liveins);
	// * Lower input variables to Alloca
	auto headerIP = headerBB->getFirstInsertionPt();
	Builder.SetInsertPoint(headerIP);
	for (auto v: liveins) {
		if (auto phi = dyn_cast<PHINode>(v)) {
			if (phi->getParent() == headerBB) {
				// always dominate whole region, no need to demote
				continue;
			}
		}
		auto a = DemoteRegToStack(*v, false, headerIP);
		// initial reset so the value does not outlive the loop backedge
		Builder.CreateStore(PoisonValue::get(v->getType()), a); 
		tmpAllocas.push_back(a);
		// DemoteRegToStack creates load from AllocaInst before every use
		// we need to add LoadInst used by extracted instruction to extracted region
		// as well
		for (auto AU: a->users()) {
			if (auto Ld = dyn_cast<LoadInst>(AU)) {
				assert(Ld->hasOneUser());
				auto U = Ld->getUniqueUndroppableUser();
				if (auto UI = dyn_cast<Instruction>(U)) {
					if (compatibleInstr.contains(UI)) {
						compatibleInstr.insert(Ld);
					}
				}
			}
		}	
	}
	
	DenseMap<Value *, Value *> toNewValMap;
	SmallVector<DomTreeUpdater::UpdateT> DTUpdates;
	copyOrMoveRegionBlocks(LI, L, proxyBB, newExitBB, toNewValMap,
								extractedRegionBBs, compatibleInstr, DTUpdates);
	buildJumpsFromProxyBeginToRegionEntryPoints(Builder, LI, DTU, MSSAU, L,
												proxyBB, newExitBB, toNewValMap,
												extractedRegionBBs, DTUpdates);
	DTU.applyUpdates(DTUpdates);
	if (DTU.hasPendingUpdates())
		DTU.flush();
	// proxyBB->getParent()->dump();
	// assert(DTU.getDomTree().verify());
	// * lower Allocas for tmp variables
	if (!tmpAllocas.empty()) {
		if (DTU.hasPendingUpdates())
			DTU.flush();
		PromoteMemToReg(tmpAllocas, DTU.getDomTree());	
	}
	returnBackLoopIDMdBeforeExit();
	return true;
}

}