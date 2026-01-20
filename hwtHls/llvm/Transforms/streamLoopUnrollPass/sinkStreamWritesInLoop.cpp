#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/sinkStreamWritesInLoop.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Transforms/Utils/LoopUtils.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/SimplifyQuery.h>

#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentOptionaStreamWrite.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamWriteMerge.h>

using namespace llvm;

namespace hwtHls {

void sinkMergableSequenceOfWritesMoveWrites(llvm::Loop &L, llvm::LoopInfo &LI,
		llvm::ScalarEvolution &SE, llvm::DominatorTree &DT,
		llvm::DomTreeUpdater &DTU, llvm::AssumptionCache &AC,
		const llvm::TargetTransformInfo &TTI, bool PreserveLCSSA,
		const SmallVector<OptionalStreamWriteCFGFragment> &mergableWriteSeqeunce,
		IRBuilder<> &Builder, BasicBlock *writesEntry, BasicBlock *writesExit) {
	DTU.flush();
	// prepare preheader for tmp variables which will be used for write data and conditions
	auto headerFirstNonPhi = L.getHeader()->getFirstNonPHIIt();
	SmallVector<AllocaInst*> tmpAllocas;
	auto *curBB = writesEntry;
	for (const OptionalStreamWriteCFGFragment &wr : mergableWriteSeqeunce) {
		SmallVector<Value*, 3> writeArgs;
		SmallVector<AllocaInst*, 4> curTmpAllocas;
		size_t argI = 0;
		// use tmp alloca to get arguments of write to section after writesEntry
		for (Use &_A : wr.write->args()) {
			Value *A = _A.get();
			if (L.isLoopInvariant(A)) {
				writeArgs.push_back(A);
			} else {
				// create tmp variable with live from header to exit
				Builder.SetInsertPoint(headerFirstNonPhi);
				auto ArgName =
						wr.write->getName()
								+ wr.write->getCalledFunction()->getArg(argI)->getName();
				auto Ty = A->getType();
				auto tmpAlloca = Builder.CreateAlloca(Ty, nullptr, ArgName);
				Builder.CreateLifetimeStart(tmpAlloca);
				Value *initVal;
				if (argI == 1) {
					// data do not need to be set to some specific value
					initVal = PoisonValue::get(Ty);
				} else {
					initVal = Builder.getIntN(Ty->getIntegerBitWidth(), 0);
				}
				Builder.CreateStore(initVal, tmpAlloca);
				Builder.SetInsertPoint(wr.write);
				Builder.CreateStore(A, tmpAlloca);
				Builder.SetInsertPoint(writesEntry->getTerminator());
				auto v = Builder.CreateLoad(Ty, tmpAlloca, ArgName);
				Builder.CreateLifetimeEnd(tmpAlloca);

				writeArgs.push_back(v);
				curTmpAllocas.push_back(tmpAlloca);
			}
			++argI;
		}
		// create enable flag for write
		Builder.SetInsertPoint(headerFirstNonPhi);
		auto int1Ty = Builder.getInt1Ty();
		auto enName = wr.write->getName() + ".streamWrite.en";
		auto tmpAlloca = Builder.CreateAlloca(int1Ty, nullptr, enName);
		Builder.CreateLifetimeStart(tmpAlloca);
		curTmpAllocas.push_back(tmpAlloca);
		Builder.CreateStore(Builder.getInt1(0), tmpAlloca);

		Builder.SetInsertPoint(wr.write);
		Builder.CreateStore(Builder.getInt1(1), tmpAlloca);

		Builder.SetInsertPoint(writesEntry->getTerminator());
		auto enCond = Builder.CreateLoad(int1Ty, tmpAlloca, enName);
		Builder.CreateLifetimeEnd(tmpAlloca);

		auto wrBBTerm = SplitBlockAndInsertIfThen(enCond, /*SplitBefore*/
		curBB->getTerminator(), /*Unreachable*/false, /*BranchWeights*/
		nullptr, &DTU, &LI);
		auto &wrBB = *wrBBTerm->getParent();
		wrBB.setName(wr.write->getParent()->getName() + ".streamWrite.sinked");
		// move write instruction to write block
		wr.write->moveBefore(wrBB, wrBBTerm->getIterator());
		// update args to use tmp alloca loads instead of original values
		argI = 0;
		for (auto *A : writeArgs) {
			wr.write->setArgOperand(argI, A);
			++argI;
		}

		tmpAllocas.insert(tmpAllocas.end(), curTmpAllocas.begin(),
				curTmpAllocas.end());
		curBB = wrBBTerm->getSuccessor(0);
	}

	DTU.flush();
	Function *F = nullptr;
	if (tmpAllocas.size()) {
		F = tmpAllocas[0]->getParent()->getParent();
	}
	llvm::PromoteMemToReg(tmpAllocas, DT, &AC);
	if (tmpAllocas.size()) {
		for (auto &BB : *F) {
			// :note: llvm-21 PromoteMemToReg somehow generates phis with
			// reversed order of operands according to block predecessors
			sortPhiOperands(BB);
		}
	}
}

void sinkMergableSequenceOfWrites(llvm::Loop &L, llvm::LoopInfo &LI,
		llvm::ScalarEvolution &SE, llvm::DominatorTree &DT,
		llvm::AssumptionCache &AC, const llvm::TargetTransformInfo &TTI,
		bool PreserveLCSSA,
		const SmallVector<OptionalStreamWriteCFGFragment> &mergableWriteSeqeunce) {
	// edges from exit blocks are likely exit from loop and continue in write sequence
	// this means that there is no post dominating block
	//
	// :note: the goal is to move all writes behind last "exit" block with the lowest amount of code replication possible
	//   specially without replication of writes
	//   However if the exit block has more than 1 successor some replication is necessary
	//   because write has to be performed on every path.

	// 1. dedicated exit blocks (should be prepared by formDedicatedExitBlocks and LoopSimplifyNormalForm)
	//   (each block which is outside of the loop and is targeted from some block from this loop has all predecessors in this loop)
	//    single backedge
	formLCSSA(L, DT, &LI, &SE); // because we need to known all liveins for hub at the end

	// 2. create a tmp variable for each write which will be assigned 0 at header and 1 on original location of a write

	// 3. if exit block has phis split it and insert new block between

	// 4. insert block on backedge and between exit block parts
	// CreateControlFlowHub
	// any variable alive on backedge or exit needs to have phi which select the value
	// because ControlFlowHub is shared block mixes exit and backedge path and SSA requires def before use

	//   |     |    ^
	//   |     |    |
	//   |   latch--|
	//   |   /
	//  exit
	//   |

	// to:
	//   |     |         ^
	//   |     |         |
	//   |   latch0      |
	//   |   /  |        |
	//  exit0  /         |
	//   |    /          |
	//  writesEntry      |
	//   |               |
	//  writesExit       |
	//   |   \           |
	//   |    \          |
	//  exit1  latch1----|
	//   |
	BasicBlock *latch0 = L.getLoopLatch();
	assert(latch0);
	BasicBlock *exit0 = L.getUniqueExitBlock();
	assert(exit0);

	// create latch 1
	BasicBlock *latch1 = SplitEdge(latch0, L.getHeader(), &DT, &LI, /*MSSAU*/
	nullptr, latch0->getName() + ".latch1");
	DomTreeUpdater DTU(&DT, DomTreeUpdater::UpdateStrategy::Lazy);
	BasicBlock *exit1 = exit0;
	exit0 = splitBlockBefore(exit0, exit0->getFirstNonPHIIt(), &DTU, &LI, /*MSSAU*/
	nullptr, exit0->getName() + ".exit1");

	BasicBlock *writesEntry = SplitEdge(exit0, exit1, &DT, &LI, /*MSSAU*/
	nullptr, latch0->getName() + ".writesEntry");
	BasicBlock *writesExit = SplitEdge(writesEntry, exit1, &DT, &LI, /*MSSAU*/
	nullptr, latch0->getName() + ".writesExit");

	IRBuilder<> Builder(&*writesEntry->begin());
	for (auto &PHI : exit0->phis()) {
		// create a new PHI in writesEntry and make all user use it instead
		auto newPhi = Builder.CreatePHI(PHI.getType(), 2, PHI.getName());
		PHI.replaceAllUsesWith(newPhi);
		newPhi->addIncoming(&PHI, exit0);
		newPhi->addIncoming(PoisonValue::get(PHI.getType()), latch0);
	}
	for (auto &PHI : L.getHeader()->phis()) {
		// create a new phi in writes entry and use it instead
		// if value is defined inside of loop
		auto val = PHI.getIncomingValueForBlock(latch1);
		if (!L.isLoopInvariant(val)) {
			auto newPhi = Builder.CreatePHI(PHI.getType(), 2, PHI.getName());
			newPhi->addIncoming(PoisonValue::get(PHI.getType()), exit0);
			newPhi->addIncoming(val, latch0);
			PHI.setIncomingValueForBlock(latch1, newPhi);
		}
	}
	// reroute latch0-latch1 to latch0-writesEntry, writesExit-latch1
	latch0->getTerminator()->replaceSuccessorWith(latch1, writesEntry);

	writesExit->getTerminator()->eraseFromParent();
	Builder.SetInsertPoint(writesEntry->getFirstNonPHIIt());
	auto *loopExitCond = Builder.CreatePHI(Builder.getInt1Ty(), 0,
			"loopExitCond");
	loopExitCond->addIncoming(Builder.getInt1(1), exit0);
	loopExitCond->addIncoming(Builder.getInt1(0), latch0);
	Builder.SetInsertPoint(writesExit);
	Builder.CreateCondBr(loopExitCond, exit1, latch1);
	// exit and after blocks were originally in parent loop now they are in L because backedge leads from latch1 which is now after writesExit
	LI.changeLoopFor(exit0, &L);
	LI.changeLoopFor(writesEntry, &L);
	LI.changeLoopFor(writesExit, &L);

	DTU.applyUpdates( { { DominatorTree::Delete, latch0, latch1 }, //
			{ DominatorTree::Insert, latch0, writesEntry }, //
			{ DominatorTree::Insert, writesExit, latch1 }, //
			});

	// move loop metadata from latch0 to latch1
	auto latch0Term = latch0->getTerminator();
	MDNode *MD = latch0Term->getMetadata(LLVMContext::MD_loop);
	latch1->getTerminator()->setMetadata(LLVMContext::MD_loop, MD);
	latch0Term->setMetadata(LLVMContext::MD_loop, nullptr);
	sinkMergableSequenceOfWritesMoveWrites(L, LI, SE, DT, DTU, AC, TTI,
			PreserveLCSSA, mergableWriteSeqeunce, Builder, writesEntry,
			writesExit);

	//llvm_unreachable("NotImplemented sinkMergableSequenceOfWrites");
}

/**
 * this loop was unrolled to satisfy throughput, that means that there are likely
 * partial writes and reads
 * * partial writes must be sinked so they may be merged to masked writes
 *   otherwise each write would require own custom shift logic to store data
 *   and to write it to IO, on the other hand if writes are sinked they may be merged
 *   which will then drastically reduce number of possible offsets for each write byte
 *   resulting in much faster compilation times
 *
 * writes of copy like pattern are usually in format
 *
 *   body.0:
 *     read0()
 *     if (c0)
 *        write0()
 *     if (eof0)
 *        continue
 *   body.1:
 *     read1()
 *     if (c1)
 *        write1()
 *     if (eof1)
 *        continue
 *   latch:
 *     continue

 *  :note: for copy the c0 and c1 is 1 and eof0, eof1 is from read0, read1
 *
 *  As write with side-effect is between reads with side-effect, this is generally non-optimizable pattern
 *  however if c1 implies c0 then code may be rewritten to:
 *    body.0:
 *      read0()
 *      if (!eof0)
 *         read1()
 *      if (c0)
 *         write0()
 *      if (c0 & !eof0 & c1)
 *         write1()
 *
 * and then to:
 *    bb0:
 *      read0()
 *      if (!eof0)
 *         read1()
 *      write(mask=concat(c0, c0 & !eof0 & c1))
 *
 * Which is trivial compared to original code
 **/
void sinkStreamWritesInLoop(llvm::Loop &L, llvm::ScalarEvolution &SE,
		llvm::DominatorTree &DT, llvm::LoopInfo &LI, llvm::AssumptionCache &AC,
		const llvm::TargetLibraryInfo &TLI,
		const llvm::TargetTransformInfo &TTI, bool PreserveLCSSA) {
	formDedicatedExitBlocks(&L, &DT, &LI, nullptr, PreserveLCSSA);
	assert(L.isLoopSimplifyForm());

	//std::map<BasicBlock*, OptionalStreamWriteCFGFragment> exitBBToWrite;
	// detect linear sequences of optional writes
	SmallVector<OptionalStreamWriteCFGFragment> writeSeqeunce;
	auto &F = *L.getBlocks()[0]->getParent();
	IRBuilder<> Builder(F.getContext());
	llvm::SimplifyQuery SQ(F.getParent()->getDataLayout(), &TLI, &DT, &AC);
	for (auto *BB : L.blocks()) {
		llvm::CallInst *wr =
				HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock(Builder,
						*BB, SQ);
		if (wr) {
			auto wrFrag = OptionalStreamWriteCFGFragment::detect(*wr);
			if (wrFrag.has_value()) {
				writeSeqeunce.push_back(wrFrag.value());
			}
		}
	}
	SmallVector<OptionalStreamWriteCFGFragment> mergableWriteSeqeunce;
	for (OptionalStreamWriteCFGFragment &wr : writeSeqeunce) {
		if (mergableWriteSeqeunce.empty()) {
			mergableWriteSeqeunce.push_back(wr);
		} else if (DT.dominates(mergableWriteSeqeunce.back().exit, wr.guard)) {
			mergableWriteSeqeunce.push_back(wr);
		} else {
			if (mergableWriteSeqeunce.size() > 1)
				sinkMergableSequenceOfWrites(L, LI, SE, DT, AC, TTI,
						PreserveLCSSA, mergableWriteSeqeunce);
			mergableWriteSeqeunce.clear();
			mergableWriteSeqeunce.push_back(wr);
		}
	}
	// for (auto W: mergableWriteSeqeunce) {
	// 	errs() << *W.write << "\n";
	// }
	if (mergableWriteSeqeunce.size() > 1) {
		sinkMergableSequenceOfWrites(L, LI, SE, DT, AC, TTI, PreserveLCSSA,
				mergableWriteSeqeunce);
	}
}

}
