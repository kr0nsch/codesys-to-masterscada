// Прогон BuildProject.cs на макете: дерево проекта → JSON (предпросмотр, не снимок MasterSCADA). C# 5.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using MasterSCADA.Scripts.Model;

public static class FakeRunner
{
    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        string node = args.Length > 0 ? args[0] : "PLC210";
        string outPath = args.Length > 1 ? args[1] : "tree.json";
        RootItem root = new RootItem();
        root.Name = "Проект";
        SystemItem sys = (SystemItem)root.AttachRaw(new SystemItem(), "Система");
        ObjectsItem objs = (ObjectsItem)root.AttachRaw(new ObjectsItem(), "Объекты");
        LibrariesItem libs = (LibrariesItem)root.AttachRaw(new LibrariesItem(), "Библиотеки");
        root.System = sys;
        root.Objects = objs;
        root.Libraries = libs;
        // Узел ПЛК из библиотеки вендора создаёт человек (MANUAL_STEPS, шаг 2); макет его имитирует.
        sys.AddController(node);
        BuildProject script = new BuildProject();
        script.RootItemModel = root;
        script.DoAction();
        StringBuilder sb = new StringBuilder();
        Dump(root, sb, 0);
        sb.Append("\n");
        File.WriteAllText(outPath, sb.ToString(), new UTF8Encoding(false));
        foreach (string line in script.ConsoleLines)
        {
            Console.WriteLine(line);
        }
        return 0;
    }

    private static string Esc(string s)
    {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        foreach (char c in s)
        {
            if (c == '"' || c == '\\') { b.Append('\\').Append(c); }
            else if (c == '\n') { b.Append("\\n"); }
            else if (c < ' ') { b.Append("\\u").Append(((int)c).ToString("x4")); }
            else { b.Append(c); }
        }
        return b.Append('"').ToString();
    }

    private static string Val(object v)
    {
        Item it = v as Item;
        if (it != null) return Esc("@" + it.FullName);
        if (v is bool) return (bool)v ? "true" : "false";
        if (v is int) return ((int)v).ToString(CultureInfo.InvariantCulture);
        if (v == null) return "null";
        return Esc(Convert.ToString(v, CultureInfo.InvariantCulture));
    }

    private static void Dump(Item item, StringBuilder sb, int depth)
    {
        string pad = new string(' ', depth * 2);
        sb.Append(pad).Append("{\"type\": ").Append(Esc(item.TypeName)).Append(", \"name\": ").Append(Esc(item.Name));
        List<KeyValuePair<string, object>> props = item.Props.ToList();
        if (props.Count > 0)
        {
            sb.Append(", \"props\": {");
            sb.Append(string.Join(", ", props.Select(p => Esc(p.Key) + ": " + Val(p.Value))));
            sb.Append("}");
        }
        List<string> links = item.Links.ToList();
        if (links.Count > 0)
        {
            sb.Append(", \"links\": [").Append(string.Join(", ", links.Select(Esc))).Append("]");
        }
        List<Item> kids = item.RawChildren.ToList();
        if (kids.Count > 0)
        {
            sb.Append(", \"children\": [\n");
            for (int i = 0; i < kids.Count; i++)
            {
                Dump(kids[i], sb, depth + 1);
                sb.Append(i + 1 < kids.Count ? ",\n" : "\n");
            }
            sb.Append(pad).Append("]");
        }
        sb.Append("}");
    }
}
