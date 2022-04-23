// based on WebAssemblyRegisterInfo.td

class GenericFpgaReg<string n> : Register<n> {
  let Namespace = "GenericFpga";
}


// The register allocation framework requires register classes have at least
// one register, so we define a few for the integer register
// classes since we otherwise don't need a physical register in those classes.
// These are also used a "types" in the generated assembly matcher.
def DUMMY_REG_0 : GenericFpgaReg<"%dummyreg.0">;


//===----------------------------------------------------------------------===//
//  Register classes
//===----------------------------------------------------------------------===//

class GenericFpgaRegClass<list<ValueType> regTypes, int alignment, dag regList>
     : RegisterClass<"GenericFpga", regTypes, alignment, regList>;


def AnyRegCls : GenericFpgaRegClass<[i128], 8, (add DUMMY_REG_0)>;