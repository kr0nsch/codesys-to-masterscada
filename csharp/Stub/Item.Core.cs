// Ядро макета: хранение свойств, дочерние элементы, поиск. Член Item, описанный в справке
// https://help.iek-digital.ru/Help-web/item.html, здесь реализован как «модель-запись». C# 5.
using System;
using System.Collections.Generic;
using System.Linq;

namespace MasterSCADA.Scripts.Model
{
    public partial class Item
    {
        private readonly List<Item> children = new List<Item>();
        private readonly SortedDictionary<string, object> props = new SortedDictionary<string, object>(StringComparer.Ordinal);
        private readonly List<string> links = new List<string>();
        private static long nextId = 1;
        private Item parent;
        private string name;
        private readonly long id;

        public Item() { id = nextId++; }

        // https://help.iek-digital.ru/Help-web/item.html
        public string Name { get { return name; } set { name = value; } }
        public Item Parent { get { return parent; } }
        public IEnumerable<Item> Childs { get { return children.ToList(); } }
        public IEnumerable<Item> OrderedChilds { get { return children.ToList(); } }
        public long Id { get { return id; } }
        public string TypeName { get { return GetType().Name; } }
        public string FullName
        {
            get { return parent == null || parent.parent == null ? name : parent.FullName + "." + name; }
        }

        public Item FindChildByName(string childName)
        {
            foreach (Item c in children) { if (c.name == childName) return c; }
            return null;
        }

        public Item GetChildByName(string childName)
        {
            Item c = FindChildByName(childName);
            if (c == null) throw new InvalidOperationException("нет дочернего элемента " + childName);
            return c;
        }

        public Item FindChildByNamePath(string path)
        {
            Item cur = this;
            foreach (string part in path.Split('.'))
            {
                cur = cur.FindChildByName(part);
                if (cur == null) return null;
            }
            return cur;
        }

        public Item GetChildByNamePath(string path)
        {
            Item c = FindChildByNamePath(path);
            if (c == null) throw new InvalidOperationException("нет элемента " + path);
            return c;
        }

        public void Delete() { if (parent != null) parent.children.Remove(this); }

        protected T GetProp<T>(string key)
        {
            object v;
            if (props.TryGetValue(key, out v) && v is T) return (T)v;
            return default(T);
        }

        protected void SetProp(string key, object value) { props[key] = value; }

        protected void ResetProp(string key)
        {
            props.Remove(key);
            props["Reset" + key] = true;
        }

        protected T AddChild<T>(string method, string childName) where T : Item, new()
        {
            T c = new T();
            c.name = childName ?? ("Новый " + typeof(T).Name + " " + (children.Count + 1));
            c.parent = this;
            children.Add(c);
            return c;
        }

        protected T FindDeep<T>(string target) where T : Item
        {
            foreach (Item c in children)
            {
                T t = c as T;
                if (t != null && c.name == target) return t;
            }
            foreach (Item c in children)
            {
                T t = c.FindDeep<T>(target);
                if (t != null) return t;
            }
            return null;
        }

        protected IEnumerable<T> ChildrenOf<T>() where T : Item { return children.OfType<T>().ToList(); }

        protected void RecordLink(string method, Item target)
        {
            links.Add(method + "->" + (target == null ? "null" : target.FullName));
        }

        protected void Unsupported(string member) { props["call:" + member] = true; }

        internal Item AttachRaw(Item child, string childName)
        {
            child.name = childName;
            child.parent = this;
            children.Add(child);
            return child;
        }

        internal IEnumerable<KeyValuePair<string, object>> Props { get { return props; } }
        internal IEnumerable<string> Links { get { return links; } }
        internal IEnumerable<Item> RawChildren { get { return children; } }
    }

    // Хост скрипта: в редакторе MasterSCADA 4D тело вставляется в DoAction(), где доступны
    // this.RootItemModel и this.WriteConsole (https://help.iek-digital.ru/Help-web/obshie_svedenia_c.html).
    public class ScriptHost
    {
        private readonly List<string> console = new List<string>();
        public RootItem RootItemModel { get; set; }
        public void WriteConsole(string text) { console.Add(text); }
        public IList<string> ConsoleLines { get { return console; } }
    }
}
