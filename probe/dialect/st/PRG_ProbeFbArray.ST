PROGRAM PRG_ProbeFbArray
VAR
    aFb : ARRAY[0..1] OF FB_ProbeEn;
    xOut : BOOL;
END_VAR
aFb[1](EN := TRUE);
xOut := aFb[1].xQ AND GVL_ProbeFb_fbShared.xQ;
END_PROGRAM
