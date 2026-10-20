PROGRAM PRG_ProbePrefix
VAR
    fb : Локальная.FB_ProbeEn;
    xOut : BOOL;
END_VAR
fb(EN := TRUE);
xOut := fb.xQ;
END_PROGRAM
