#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/InstCombineABC1bLogicPass.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/IR/Analysis.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Instruction.h>

// abc related
#include <aig/aig/aig.h>
#include <base/abc/abc.h>
#include <base/io/ioAbc.h>
#include <base/main/abcapis.h>
#include <base/main/main.h>
#include <map/mio/mio.h>
#include <opt/dar/dar.h>

#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/abcAigToLlvmIr.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
// #include <llvm/IR/Verifier.h>

using namespace llvm;

// [SYNCHRONIZED]
//  * hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/InstCombineABC1bLogicPass.cpp
//  * hwtHls.netlist.abc.optScripts
//  * hwtHls.netlist.transformation.simplifyExpr.simplifyAbc

ABC_NAMESPACE_HEADER_START
extern Abc_Ntk_t *Abc_NtkDRewrite(Abc_Ntk_t *pNtk, Dar_RwrPar_t *pPars);
extern Abc_Ntk_t *Abc_NtkDRefactor(Abc_Ntk_t *pNtk, Dar_RefPar_t *pPars);
ABC_NAMESPACE_HEADER_END

namespace hwtHls {
struct DRewritePars : Dar_RwrPar_t {
	DRewritePars(bool fUpdateLevel, bool fUseZeros) {
		nCutsMax = 8;
		nSubgMax = 5;
		nMinSaved = fUseZeros ? 0 : 1;
		fFanout = true;
		this->fUpdateLevel = fUpdateLevel;
		this->fUseZeros = fUseZeros;
		fPower = false;
		fRecycle = true;
		fVerbose = false;
		fVeryVerbose = false;
	}
};

struct DRefactorPars : Dar_RefPar_t {
	DRefactorPars(bool fUpdateLevel, bool fUseZeros, bool fExtend) {
		nMffcMin = 2;
		nLeafMax = 12;
		nCutsMax = 5;
		this->fExtend = fExtend;
		this->fUpdateLevel = fUpdateLevel;
		this->fUseZeros = fUseZeros;
		fVerbose = false;
		fVeryVerbose = false;
	}
};

Abc_Ntk_t *abcCmd_resyn2(Abc_Ntk_t *net) {
	// abc standard scripts
	// resyn2      "b; rw; rf; b; rw; rwz; b; rfz; rwz; b"
	// with replaced https://github.com/YosysHQ/yosys/issues/4039
	//   rf -> drf,-l
	//   rw -> drw,-l
	net = Abc_NtkBalance(net, false, false, true);

	{
		DRewritePars pars(true, false);
		net = Abc_NtkDRewrite(net, &pars);
	}
	{
		DRefactorPars pars(true, false, true);
		net = Abc_NtkDRefactor(net, &pars);
	}

	net = Abc_NtkBalance(net, false, false, true);

	{
		DRewritePars pars(true, false);
		net = Abc_NtkDRewrite(net, &pars);
	}
	{
		DRewritePars pars(true, true); // rewrite -z
		net = Abc_NtkDRewrite(net, &pars);
	}

	net = Abc_NtkBalance(net, false, false, true);

	{
		DRefactorPars pars(true, true, true); // refactor -z
		net = Abc_NtkDRefactor(net, &pars);
	}
	{
		DRewritePars pars(true, true); // rewrite -z
		net = Abc_NtkDRewrite(net, &pars);
	}

	if (!Abc_NtkRewrite(net, true, true, false, false,
						false)) { // hwtHls specific
		throw std::runtime_error("Abc_NtkRewrite has failed");
	}
	if (!Abc_NtkRefactor(net, 10, 1, 16, true, false, false,
						 false)) { // hwtHls specific
		throw std::runtime_error("Abc_NtkRefactor has failed");
	}

	net = Abc_NtkBalance(net, false, false, true);
	return net;
}

Abc_Ntk_t *abcCmd_compress2(Abc_Ntk_t *net) {
	// abc standard scripts
	// compress2   "b -l; rw -l; rf -l; b -l; rw -l; rwz -l; b -l; rfz -l; rwz
	// -l; b -l" with replaced https://github.com/YosysHQ/yosys/issues/4039
	//   rf -> drf,-l
	//   rw -> drw,-l
	net = Abc_NtkBalance(net, false, false, false); // balance -l

	{
		DRewritePars pars(false, false); // rewrite -l
		net = Abc_NtkDRewrite(net, &pars);
	}
	{
		DRefactorPars pars(false, false, true);
		net = Abc_NtkDRefactor(net, &pars);
	}

	net = Abc_NtkBalance(net, false, false, false); // balance -l

	{
		DRewritePars pars(false, false); // rewrite -l
		net = Abc_NtkDRewrite(net, &pars);
	}
	{
		DRewritePars pars(false, true); // rewrite -z -l
		net = Abc_NtkDRewrite(net, &pars);
	}

	net = Abc_NtkBalance(net, false, false, false); // balance -l

	{
		DRewritePars pars(false, true); // rewrite -z -l
		net = Abc_NtkDRewrite(net, &pars);
	}

	if (!Abc_NtkRewrite(net, false, false, false, false,
						false)) { // hwtHls specific
		throw std::runtime_error("Abc_NtkRewrite has failed");
	}
	if (!Abc_NtkRefactor(net, 10, 1, 16, false, false, false,
						 false)) { // hwtHls specific
		throw std::runtime_error("Abc_NtkRefactor has failed");
	}

	net = Abc_NtkBalance(net, false, false, false); // balance -l
	return net;
}

void InstCombineABC1bLogicPass::runOptScripts(LlvmIrToAbcAig &toAbc) {
	Abc_AigCleanup(toAbc.aig);
	toAbc.net = abcCmd_resyn2(toAbc.net);
	toAbc.net = abcCmd_compress2(toAbc.net);
}

void InstCombineABC1bLogicPass::findSelectedInstructions(
	Function &F, SetVector<Instruction *> &selected,
	SetVector<Instruction *> &inputs, SetVector<Instruction *> &outputs) {
	for (auto &BB : F) {
		for (auto &I : BB) {
			if (!I.getType()->isIntegerTy(1))
				continue;

			if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
				switch (BO->getOpcode()) {
				case Instruction::And:
				case Instruction::Or:
				case Instruction::Xor:
					selected.insert(BO);
				default:
					break;
				}
			} else if (isa<SelectInst>(&I)) {
				selected.insert(&I);
			} else if (auto *icmp = dyn_cast<ICmpInst>(&I)) {
				if (!I.getOperand(0)->getType()->isIntegerTy(1))
					continue;
				switch (icmp->getPredicate()) {
				case CmpInst::ICMP_EQ:
				case CmpInst::ICMP_NE:
					selected.insert(icmp);
					break;
				default:
					break;
				}
			}
		}
	}
	for (auto *I : selected) {
		for (auto *Op : I->operand_values()) {
			if (auto *OpI = dyn_cast<Instruction>(Op)) {
				if (!selected.contains(OpI)) {
					inputs.insert(OpI);
				}
			}
		}
		for (auto U : I->users()) {
			if (auto UI = dyn_cast<Instruction>(U)) {
				if (selected.contains(UI)) {
					continue;
				}
			}
			outputs.insert(I);
			break;
		}
	}
}

PreservedAnalyses InstCombineABC1bLogicPass::run(Function &F,
												 FunctionAnalysisManager &AM) {
	auto &DT = AM.getResult<DominatorTreeAnalysis>(F);
	auto &TLI = AM.getResult<TargetLibraryAnalysis>(F);
	//errs() << "InstCombineABC1bLogicPass 0:\n";
	//F.dump();
	//errs() << "\n";
	//assert(!verifyFunction(F, &errs()));
	// assert(DT.verify());
	SetVector<Instruction *> selected;
	SetVector<Instruction *> inputs;
	SetVector<Instruction *> outputs;
	findSelectedInstructions(F, selected, inputs, outputs);
	if (outputs.empty())
		return PreservedAnalyses::all();

	LlvmIrToAbcAig toAbc;
	toAbc.translate(inputs, outputs);
	runOptScripts(toAbc);

	AbcAigToLlvmIr toLlvm(F, toAbc.net, toAbc.ioMap, F.getEntryBlock(), DT);
	bool change = toLlvm.translate();
	if (change) {
		DceWorklist DCE(&TLI);
		for (auto *I : outputs) {
			DCE.insert(*I);
		}
		DCE.runToCompletion();
	}
	// errs() << "InstCombineABC1bLogicPass 1:\n";
	// F.dump();
	// errs() << "\n";
	// assert(!verifyFunction(F, &errs()));
	// errs()
	// 	<< "##############################################################\n";
	if (!change) {
		return PreservedAnalyses::all();
	}

	auto PA = PreservedAnalyses();
	PA.preserve<GlobalsAA>();
	PA.preserveSet<CFGAnalyses>();
	return PA;
}
}