PROGRAM PRG_ProbeEnum
VAR
    eState : E_ProbeState := E_ProbeState.Run;
    iOut : INT;
END_VAR
CASE eState OF
    E_ProbeState.Idle:
        iOut := 0;
    E_ProbeState.Run:
        iOut := 10;
ELSE
    iOut := -1;
END_CASE;
END_PROGRAM
