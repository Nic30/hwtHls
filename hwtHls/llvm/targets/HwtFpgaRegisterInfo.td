// based on WebAssemblyRegisterInfo.td

class HwtFpgaReg<string n> : Register<n> {
  let Namespace = "HwtFpga";
}


// The register allocation framework requires register classes have at least
// one register, so we define a few for the integer register
// classes since we otherwise don't need a physical register in those classes.
// These are also used a "types" in the generated assembly matcher.
foreach I = 0-4096 in
	def DUMMY_REG_#I : HwtFpgaReg<"%dummyreg."#I>;


//===----------------------------------------------------------------------===//
//  Register classes
//===----------------------------------------------------------------------===//

class HwtFpgaRegClass<list<ValueType> regTypes, int alignment, dag regList>
     : RegisterClass<"HwtFpga", regTypes, alignment, regList>;

// v1024i32 is largest working type available (smaller types do require reg. spliting more ofter, wider types do not work due LLVM bug)
def anyregcls : HwtFpgaRegClass<[v1024i32], 1, (add (sequence "DUMMY_REG_%u", 0, 4096))>;