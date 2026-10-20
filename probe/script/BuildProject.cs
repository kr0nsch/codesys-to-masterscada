// Обёртка для макета API (csharp/Stub) и FakeRunner. В MasterSCADA 4D вставляется только тело
// DoAction() из DoAction.body.cs — класс редактора задаёт среда.
using System;
using MasterSCADA.Scripts.Model;

public class BuildProject : ScriptHost
{
    public void DoAction()
    {
        // создано cds2ms 0.1.0 · source.cds.xml · SHA-256 67b4e46aed09769b9ccf0090a7c9dce961f985a8e2f76c7b84f2a53ff6004ee6
        // Тело метода DoAction() элемента «Скрипт» MasterSCADA 4D (https://help.iek-digital.ru/Help-web/script_c.html).
        // Идемпотентно: повторный запуск ничего не дублирует. Приоритеты задач не трогает (https://help.iek-digital.ru/Help-web/zadachi.html).
        var root = this.RootItemModel; // https://help.iek-digital.ru/Help-web/obshie_svedenia_c.html
        ControllerItem node = root.System.FindController("PLC210"); // https://help.iek-digital.ru/Help-web/systemitem.html
        if (node == null)
        {
            this.WriteConsole("cds2ms: узел PLC210 не найден — добавьте узел ПЛК из библиотеки вендора (MANUAL_STEPS, шаг 2)");
            return;
        }
        int created = 0;
        // задача TaskFast (CODESYS: Cyclic, 10 мс)
        TaskItem task1 = node.FindChildByName("TaskFast") as TaskItem; // https://help.iek-digital.ru/Help-web/item.html
        if (task1 == null) { task1 = node.AddTask("TaskFast"); created++; } // https://help.iek-digital.ru/Help-web/controlleritem.html
        task1.Period = 10; // https://help.iek-digital.ru/Help-web/taskitem.html
        task1.ResetTranslatorType(); // по умолчанию Lua (https://help.iek-digital.ru/Help-web/zadachi.html)
        task1.ResetPriority(); // приоритет не переносится: неверный может повесить ПЛК
        ObjectItem disp1 = root.Objects.FindObject("migTask_TaskFast"); // https://help.iek-digital.ru/Help-web/objectsitem.html
        if (disp1 == null) { disp1 = root.Objects.AddObject("migTask_TaskFast"); created++; }
        disp1.TaskRef = task1; // https://help.iek-digital.ru/Help-web/objectitem.html
        disp1.ControllerRef = node;
        ProgramSTItem prg1 = disp1.FindChildByName("migDispatch") as ProgramSTItem;
        if (prg1 == null) { prg1 = disp1.AddProgramST("migDispatch"); created++; } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        prg1.Text = "PLC210.PRG_Main();\nPLC210.PRG_Permissives();\nPLC210.PRG_PumpInterlock();\n"; // https://help.iek-digital.ru/Help-web/programstitem.html; вызов программы узла — https://help.iek-digital.ru/Help-web/vyzov_programm_obektov.html [L]
        // задача TaskSlow (CODESYS: Cyclic, 200 мс)
        TaskItem task2 = node.FindChildByName("TaskSlow") as TaskItem; // https://help.iek-digital.ru/Help-web/item.html
        if (task2 == null) { task2 = node.AddTask("TaskSlow"); created++; } // https://help.iek-digital.ru/Help-web/controlleritem.html
        task2.Period = 200; // https://help.iek-digital.ru/Help-web/taskitem.html
        task2.ResetTranslatorType(); // по умолчанию Lua (https://help.iek-digital.ru/Help-web/zadachi.html)
        task2.ResetPriority(); // приоритет не переносится: неверный может повесить ПЛК
        ObjectItem disp2 = root.Objects.FindObject("migTask_TaskSlow"); // https://help.iek-digital.ru/Help-web/objectsitem.html
        if (disp2 == null) { disp2 = root.Objects.AddObject("migTask_TaskSlow"); created++; }
        disp2.TaskRef = task2; // https://help.iek-digital.ru/Help-web/objectitem.html
        disp2.ControllerRef = node;
        ProgramSTItem prg2 = disp2.FindChildByName("migDispatch") as ProgramSTItem;
        if (prg2 == null) { prg2 = disp2.AddProgramST("migDispatch"); created++; } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        prg2.Text = "PLC210.PRG_FillSeq();\nPLC210.PRG_CipSeq();\n"; // https://help.iek-digital.ru/Help-web/programstitem.html; вызов программы узла — https://help.iek-digital.ru/Help-web/vyzov_programm_obektov.html [L]
        // задача TaskAlarm (CODESYS: Event, 20 мс)
        TaskItem task3 = node.FindChildByName("TaskAlarm") as TaskItem; // https://help.iek-digital.ru/Help-web/item.html
        if (task3 == null) { task3 = node.AddTask("TaskAlarm"); created++; } // https://help.iek-digital.ru/Help-web/controlleritem.html
        task3.Period = 20; // https://help.iek-digital.ru/Help-web/taskitem.html
        task3.ResetTranslatorType(); // по умолчанию Lua (https://help.iek-digital.ru/Help-web/zadachi.html)
        task3.ResetPriority(); // приоритет не переносится: неверный может повесить ПЛК
        ObjectItem disp3 = root.Objects.FindObject("migTask_TaskAlarm"); // https://help.iek-digital.ru/Help-web/objectsitem.html
        if (disp3 == null) { disp3 = root.Objects.AddObject("migTask_TaskAlarm"); created++; }
        disp3.TaskRef = task3; // https://help.iek-digital.ru/Help-web/objectitem.html
        disp3.ControllerRef = node;
        ProgramSTItem prg3 = disp3.FindChildByName("migDispatch") as ProgramSTItem;
        if (prg3 == null) { prg3 = disp3.AddProgramST("migDispatch"); created++; } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        prg3.Text = "PLC210.PRG_OopDemo();\n"; // https://help.iek-digital.ru/Help-web/programstitem.html; вызов программы узла — https://help.iek-digital.ru/Help-web/vyzov_programm_obektov.html [L]
        ProgramItem call1 = node.FindChildByName("PRG_Main") as ProgramItem;
        if (call1 != null) { call1.ExecutionMethod = FBExecuteTypes.OnCall; } // https://help.iek-digital.ru/Help-web/programitem.html
        else { this.WriteConsole("cds2ms: программа PRG_Main не найдена — сначала импорт PLCopen XML (шаг 3)"); }
        ProgramItem call2 = node.FindChildByName("PRG_Permissives") as ProgramItem;
        if (call2 != null) { call2.ExecutionMethod = FBExecuteTypes.OnCall; } // https://help.iek-digital.ru/Help-web/programitem.html
        else { this.WriteConsole("cds2ms: программа PRG_Permissives не найдена — сначала импорт PLCopen XML (шаг 3)"); }
        ProgramItem call3 = node.FindChildByName("PRG_PumpInterlock") as ProgramItem;
        if (call3 != null) { call3.ExecutionMethod = FBExecuteTypes.OnCall; } // https://help.iek-digital.ru/Help-web/programitem.html
        else { this.WriteConsole("cds2ms: программа PRG_PumpInterlock не найдена — сначала импорт PLCopen XML (шаг 3)"); }
        ProgramItem call4 = node.FindChildByName("PRG_FillSeq") as ProgramItem;
        if (call4 != null) { call4.ExecutionMethod = FBExecuteTypes.OnCall; } // https://help.iek-digital.ru/Help-web/programitem.html
        else { this.WriteConsole("cds2ms: программа PRG_FillSeq не найдена — сначала импорт PLCopen XML (шаг 3)"); }
        ProgramItem call5 = node.FindChildByName("PRG_CipSeq") as ProgramItem;
        if (call5 != null) { call5.ExecutionMethod = FBExecuteTypes.OnCall; } // https://help.iek-digital.ru/Help-web/programitem.html
        else { this.WriteConsole("cds2ms: программа PRG_CipSeq не найдена — сначала импорт PLCopen XML (шаг 3)"); }
        ProgramItem call6 = node.FindChildByName("PRG_OopDemo") as ProgramItem;
        if (call6 != null) { call6.ExecutionMethod = FBExecuteTypes.OnCall; } // https://help.iek-digital.ru/Help-web/programitem.html
        else { this.WriteConsole("cds2ms: программа PRG_OopDemo не найдена — сначала импорт PLCopen XML (шаг 3)"); }
        this.WriteConsole("cds2ms: задач 3, создано элементов " + created);
    }
}
