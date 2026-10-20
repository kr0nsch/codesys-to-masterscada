// Макет внешней объектной модели MasterSCADA 4D 1.3.10 — построен tools/gen_stub.py из csharp/api-snapshot.tsv.
// Не править вручную. Члены — по страницам справки https://help.iek-digital.ru/Help-web/ (адрес у члена).
// [L] — класс, на который ссылается справка, без своей страницы в снимке: пустой наследник Item.
using System;
using System.Collections.Generic;

namespace MasterSCADA.Scripts.Model
{
    // https://help.iek-digital.ru/Help-web/ (возможные значения из таблицы свойства)
    public enum AccessTypes { Input, Output, InOut }

    // https://help.iek-digital.ru/Help-web/ (возможные значения из таблицы свойства)
    public enum EdgeTypes { NONE, R_EDGE, F_EDGE }

    // https://help.iek-digital.ru/Help-web/ (возможные значения из таблицы свойства)
    public enum ExecutePlaces { ObjectTask, ControllerTask, ScreenTask }

    // https://help.iek-digital.ru/Help-web/ (возможные значения из таблицы свойства)
    public enum FBExecuteTypes { Periodic, OnCall, OnStartup }

    // https://help.iek-digital.ru/Help-web/ (возможные значения из таблицы свойства)
    public enum ModifierTypes { RETAIN, NON_RETAIN, CONSTANT, NONE }

    // https://help.iek-digital.ru/Help-web/ (возможные значения из таблицы свойства)
    public enum RWAccessTypes { Read, Write, ReadWrite }

    // https://help.iek-digital.ru/Help-web/ (возможные значения из таблицы свойства)
    public enum TranslatorType { Lua, CSharp }

    // [L] страницы в снимке нет
    public class AlarmUsageItem : Item { }

    // [L] страницы в снимке нет
    public class ArchiveItem : Item { }

    // [L] страницы в снимке нет
    public class ArchiveMemoryItem : Item { }

    // [L] страницы в снимке нет
    public class ArchiveTemplateItem : Item { }

    // [L] страницы в снимке нет
    public class CommonItem : Item { }

    // [L] страницы в снимке нет
    public class DirectoryArchiveItem : Item { }

    // [L] страницы в снимке нет
    public class EventsArchiveItem : Item { }

    // [L] страницы в снимке нет
    public class ExternalChannelItem : Item { }

    // [L] страницы в снимке нет
    public class ObjectInstanceItem : Item { }

    // [L] страницы в снимке нет (наследование выведено из имени: AddProgramST и др. — у ObjectOrTagBase)
    public class ObjectOrTagInstanceItem : ObjectOrTagBase { }

    // [L] страницы в снимке нет (наследование выведено из имени: AddProgramST и др. — у ObjectOrTagBase)
    public class ObjectOrTagItem : ObjectOrTagBase { }

    // [L] страницы в снимке нет
    public class POUTypeDeclarationItem : Item { }

    // [L] страницы в снимке нет
    public class POUTypeUsageItem : Item { }

    // [L] страницы в снимке нет
    public class ProgramCsharpItem : Item { }

    // [L] страницы в снимке нет
    public class ProtocolItem : Item { }

    // [L] страницы в снимке нет
    public class ReportItem : Item { }

    // [L] страницы в снимке нет
    public class ScaleItem : Item { }

    // [L] страницы в снимке нет
    public class ScreenItem : Item { }

    // [L] страницы в снимке нет
    public class SettingItem : Item { }

    // [L] страницы в снимке нет
    public class TagFolder : Item { }

    // [L] страницы в снимке нет
    public class TagItem : Item { }

    // [L] страницы в снимке нет
    public class ViewAccessParamItem : Item { }

    // [L] страницы в снимке нет
    public class ViewDeclarationInObjectItem : Item { }

    // [L] страницы в снимке нет
    public class ViewUsageParamItem : Item { }

    // https://help.iek-digital.ru/Help-web/item.html
    public partial class Item
    {
        public void DeleteItemById(long a0) { Unsupported("DeleteItemById"); } // https://help.iek-digital.ru/Help-web/item.html
        public void Duplicate(int a0) { Unsupported("Duplicate"); } // https://help.iek-digital.ru/Help-web/item.html
        public Item FindChildByRefName(string a0) { return FindDeep<Item>(a0); } // https://help.iek-digital.ru/Help-web/item.html
        public Item FindChildByRefNamePath(string a0) { return FindDeep<Item>(a0); } // https://help.iek-digital.ru/Help-web/item.html
        public Item FindItemByFullName(string a0) { return FindDeep<Item>(a0); } // https://help.iek-digital.ru/Help-web/item.html
        public Item FindItemByFullRefName(string a0) { return FindDeep<Item>(a0); } // https://help.iek-digital.ru/Help-web/item.html
        public Item FindItemById(long a0) { Unsupported("FindItemById"); return default(Item); } // https://help.iek-digital.ru/Help-web/item.html
        public Item FindNestedChildByName(string a0) { return FindDeep<Item>(a0); } // https://help.iek-digital.ru/Help-web/item.html
        public Item FindNestedChildByRefName(string a0) { return FindDeep<Item>(a0); } // https://help.iek-digital.ru/Help-web/item.html
        public Item GetChildByRefName(string a0) { Item x = FindDeep<Item>(a0); if (x == null) throw new InvalidOperationException("не найден: " + a0); return x; } // https://help.iek-digital.ru/Help-web/item.html
        public Item GetChildByRefNamePath(string a0) { Item x = FindDeep<Item>(a0); if (x == null) throw new InvalidOperationException("не найден: " + a0); return x; } // https://help.iek-digital.ru/Help-web/item.html
        public Item GetItemByFullName(string a0) { Item x = FindDeep<Item>(a0); if (x == null) throw new InvalidOperationException("не найден: " + a0); return x; } // https://help.iek-digital.ru/Help-web/item.html
        public Item GetItemByFullRefName(string a0) { Item x = FindDeep<Item>(a0); if (x == null) throw new InvalidOperationException("не найден: " + a0); return x; } // https://help.iek-digital.ru/Help-web/item.html
        public Item GetItemById(long a0) { Unsupported("GetItemById"); return default(Item); } // https://help.iek-digital.ru/Help-web/item.html
        public Item GetNestedChildByName(string a0) { Item x = FindDeep<Item>(a0); if (x == null) throw new InvalidOperationException("не найден: " + a0); return x; } // https://help.iek-digital.ru/Help-web/item.html
        public Item GetNestedChildByRefName(string a0) { Item x = FindDeep<Item>(a0); if (x == null) throw new InvalidOperationException("не найден: " + a0); return x; } // https://help.iek-digital.ru/Help-web/item.html
        public bool ResetComment() { ResetProp("Comment"); return true; } // https://help.iek-digital.ru/Help-web/item.html
        public bool ResetDescription() { ResetProp("Description"); return true; } // https://help.iek-digital.ru/Help-web/item.html
        public bool ResetTag() { ResetProp("Tag"); return true; } // https://help.iek-digital.ru/Help-web/item.html
        public IEnumerable<Item> BackwardLinks { get { return ChildrenOf<Item>(); } } // https://help.iek-digital.ru/Help-web/item.html
        public string Comment { get { return GetProp<string>("Comment"); } set { SetProp("Comment", value); } } // https://help.iek-digital.ru/Help-web/item.html
        public string Description { get { return GetProp<string>("Description"); } set { SetProp("Description", value); } } // https://help.iek-digital.ru/Help-web/item.html
        public IEnumerable<Item> ForwardLinks { get { return ChildrenOf<Item>(); } } // https://help.iek-digital.ru/Help-web/item.html
        public string FullRefName { get { return GetProp<string>("FullRefName"); } set { SetProp("FullRefName", value); } } // https://help.iek-digital.ru/Help-web/item.html
        public int Position { get { return GetProp<int>("Position"); } set { SetProp("Position", value); } } // https://help.iek-digital.ru/Help-web/item.html
        public string RefName { get { return GetProp<string>("RefName"); } set { SetProp("RefName", value); } } // https://help.iek-digital.ru/Help-web/item.html
        public string Tag { get { return GetProp<string>("Tag"); } set { SetProp("Tag", value); } } // https://help.iek-digital.ru/Help-web/item.html
        public IEnumerable<Item> UngroupedChilds { get { return ChildrenOf<Item>(); } } // https://help.iek-digital.ru/Help-web/item.html
        public Item ValueGetsItem { get { return GetProp<Item>("ValueGetsItem"); } set { SetProp("ValueGetsItem", value); } } // https://help.iek-digital.ru/Help-web/item.html
        public IEnumerable<Item> ValueSendItems { get { return ChildrenOf<Item>(); } } // https://help.iek-digital.ru/Help-web/item.html
    }

    // https://help.iek-digital.ru/Help-web/attributeitem.html
    public partial class AttributeItem : VariableItem
    {
        public void ResetAccess() { ResetProp("Access"); } // https://help.iek-digital.ru/Help-web/attributeitem.html
        public void ResetSaving() { ResetProp("Saving"); } // https://help.iek-digital.ru/Help-web/attributeitem.html
        public RWAccessTypes Access { get { return GetProp<RWAccessTypes>("Access"); } set { SetProp("Access", value); } } // https://help.iek-digital.ru/Help-web/attributeitem.html
        public ModifierTypes Saving { get { return GetProp<ModifierTypes>("Saving"); } set { SetProp("Saving", value); } } // https://help.iek-digital.ru/Help-web/attributeitem.html
    }

    // https://help.iek-digital.ru/Help-web/channelitem.html
    public partial class ChannelItem : Item
    {
        public void AddLink(ChannelItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public void AddLink(TagInstanceItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public void AddLink(TagItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public void AddLink(VariableItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public void DeleteArchiveTemplateType() { ResetProp("ArchiveTemplateType"); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public void DeleteScaleType() { ResetProp("ScaleType"); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public AttributeItem FindAttribute(string a0) { return FindDeep<AttributeItem>(a0); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetAccess() { ResetProp("Access"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetHistorizing() { ResetProp("Historizing"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetInheritFromScale() { ResetProp("InheritFromScale"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetSourceMax() { ResetProp("SourceMax"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetSourceMin() { ResetProp("SourceMin"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetTargetMax() { ResetProp("TargetMax"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetTargetMin() { ResetProp("TargetMin"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool ResetUseScaling() { ResetProp("UseScaling"); return true; } // https://help.iek-digital.ru/Help-web/channelitem.html
        public void TryAddLink(Item a0) { RecordLink("TryAddLink", a0); } // https://help.iek-digital.ru/Help-web/channelitem.html
        public AccessTypes Access { get { return GetProp<AccessTypes>("Access"); } set { SetProp("Access", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public ArchiveTemplateItem ArchiveTemplate { get { return GetProp<ArchiveTemplateItem>("ArchiveTemplate"); } set { SetProp("ArchiveTemplate", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public string ArchiveTemplateType { get { return GetProp<string>("ArchiveTemplateType"); } set { SetProp("ArchiveTemplateType", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public Item DataSource { get { return GetProp<Item>("DataSource"); } set { SetProp("DataSource", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool Historizing { get { return GetProp<bool>("Historizing"); } set { SetProp("Historizing", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool InheritFromScale { get { return GetProp<bool>("InheritFromScale"); } set { SetProp("InheritFromScale", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public ScaleItem Scale { get { return GetProp<ScaleItem>("Scale"); } set { SetProp("Scale", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public string ScaleType { get { return GetProp<string>("ScaleType"); } set { SetProp("ScaleType", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public IEnumerable<SettingItem> Settings { get { return ChildrenOf<SettingItem>(); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public string SourceMax { get { return GetProp<string>("SourceMax"); } set { SetProp("SourceMax", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public string SourceMin { get { return GetProp<string>("SourceMin"); } set { SetProp("SourceMin", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public string TargetMax { get { return GetProp<string>("TargetMax"); } set { SetProp("TargetMax", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public string TargetMin { get { return GetProp<string>("TargetMin"); } set { SetProp("TargetMin", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
        public bool UseScaling { get { return GetProp<bool>("UseScaling"); } set { SetProp("UseScaling", value); } } // https://help.iek-digital.ru/Help-web/channelitem.html
    }

    // https://help.iek-digital.ru/Help-web/controlleritem.html
    public partial class ControllerItem : ObjectOrTagBase
    {
        public ArchiveItem AddArchive(string a0 = null) { return AddChild<ArchiveItem>("AddArchive", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ArchiveMemoryItem AddArchiveMemory(string a0 = null) { return AddChild<ArchiveMemoryItem>("AddArchiveMemory", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public DirectoryArchiveItem AddDirectoryArchive(string a0 = null) { return AddChild<DirectoryArchiveItem>("AddDirectoryArchive", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ExternalChannelItem AddExternalChannel(string a0 = null) { return AddChild<ExternalChannelItem>("AddExternalChannel", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ProtocolItem AddNodeToNodeConnection(string a0 = null) { return AddChild<ProtocolItem>("AddNodeToNodeConnection", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public AttributeItem AddParameter(string a0 = null) { return AddChild<AttributeItem>("AddParameter", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ProtocolItem AddProtocol(string a0 = null) { return AddChild<ProtocolItem>("AddProtocol", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ProtocolItem AddReservation(string a0 = null) { return AddChild<ProtocolItem>("AddReservation", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ProtocolItem AddSavingState(string a0 = null) { return AddChild<ProtocolItem>("AddSavingState", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ScreenItem AddScreen(string a0 = null) { return AddChild<ScreenItem>("AddScreen", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public TaskItem AddTask(string a0 = null) { return AddChild<TaskItem>("AddTask", a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public AttributeItem FindParameter(string a0) { return FindDeep<AttributeItem>(a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public ProtocolItem FindProtocol(string a0) { return FindDeep<ProtocolItem>(a0); } // https://help.iek-digital.ru/Help-web/controlleritem.html
        public IEnumerable<ProtocolItem> Protocols { get { return ChildrenOf<ProtocolItem>(); } } // https://help.iek-digital.ru/Help-web/controlleritem.html
    }

    // https://help.iek-digital.ru/Help-web/librariesitem.html
    public partial class LibrariesItem : CommonItem
    {
    }

    // https://help.iek-digital.ru/Help-web/localvaritem.html
    public partial class LocalVarItem : Item
    {
        public void DeleteScaleType() { ResetProp("ScaleType"); } // https://help.iek-digital.ru/Help-web/localvaritem.html
        public void ResetInitialValue() { ResetProp("InitialValue"); } // https://help.iek-digital.ru/Help-web/localvaritem.html
        public void ResetValueType() { ResetProp("ValueType"); } // https://help.iek-digital.ru/Help-web/localvaritem.html
        public object InitialValue { get { return GetProp<object>("InitialValue"); } set { SetProp("InitialValue", value); } } // https://help.iek-digital.ru/Help-web/localvaritem.html
        public ScaleItem Scale { get { return GetProp<ScaleItem>("Scale"); } set { SetProp("Scale", value); } } // https://help.iek-digital.ru/Help-web/localvaritem.html
        public string ScaleType { get { return GetProp<string>("ScaleType"); } set { SetProp("ScaleType", value); } } // https://help.iek-digital.ru/Help-web/localvaritem.html
        public string ValueType { get { return GetProp<string>("ValueType"); } set { SetProp("ValueType", value); } } // https://help.iek-digital.ru/Help-web/localvaritem.html
    }

    // https://help.iek-digital.ru/Help-web/objectfolder.html
    public partial class ObjectFolder : TagFolder
    {
        public ObjectItem AddObject(string a0 = null) { return AddChild<ObjectItem>("AddObject", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
        public TagItem AddTagBase(string a0 = null) { return AddChild<TagItem>("AddTagBase", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
        public TagInstanceItem AddTagInteger(string a0 = null) { return AddChild<TagInstanceItem>("AddTagInteger", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
        public TagItem AddTagIntegerInheritance(string a0 = null) { return AddChild<TagItem>("AddTagIntegerInheritance", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
        public TagInstanceItem AddTagLogical(string a0 = null) { return AddChild<TagInstanceItem>("AddTagLogical", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
        public TagItem AddTagLogicalInheritance(string a0 = null) { return AddChild<TagItem>("AddTagLogicalInheritance", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
        public TagInstanceItem AddTagReal(string a0 = null) { return AddChild<TagInstanceItem>("AddTagReal", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
        public TagItem AddTagRealInheritance(string a0 = null) { return AddChild<TagItem>("AddTagRealInheritance", a0); } // https://help.iek-digital.ru/Help-web/objectfolder.html
    }

    // https://help.iek-digital.ru/Help-web/objectitem.html
    public partial class ObjectItem : ObjectOrTagItem
    {
        public ObjectFolder AddFolder(string a0 = null) { return AddChild<ObjectFolder>("AddFolder", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectItem AddObject(string a0 = null) { return AddChild<ObjectItem>("AddObject", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagItem AddTagBase(string a0 = null) { return AddChild<TagItem>("AddTagBase", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagInstanceItem AddTagInteger(string a0 = null) { return AddChild<TagInstanceItem>("AddTagInteger", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagItem AddTagIntegerInheritance(string a0 = null) { return AddChild<TagItem>("AddTagIntegerInheritance", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagInstanceItem AddTagLogical(string a0 = null) { return AddChild<TagInstanceItem>("AddTagLogical", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagItem AddTagLogicalInheritance(string a0 = null) { return AddChild<TagItem>("AddTagLogicalInheritance", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagInstanceItem AddTagReal(string a0 = null) { return AddChild<TagInstanceItem>("AddTagReal", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagItem AddTagRealInheritance(string a0 = null) { return AddChild<TagItem>("AddTagRealInheritance", a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectItem CopyTo(ObjectItem a0) { Unsupported("CopyTo"); return default(ObjectItem); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectItem FindObject(string a0) { return FindDeep<ObjectItem>(a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagItem FindTag(string a0) { return FindDeep<TagItem>(a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TagInstanceItem FindTagInstance(string a0) { return FindDeep<TagInstanceItem>(a0); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectItem InsertInheritorTo(ObjectFolder a0) { Unsupported("InsertInheritorTo"); return default(ObjectItem); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectItem InsertInheritorTo(ObjectItem a0) { Unsupported("InsertInheritorTo"); return default(ObjectItem); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectItem InsertInheritorTo(ObjectsItem a0) { Unsupported("InsertInheritorTo"); return default(ObjectItem); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectInstanceItem InsertInstanceTo(ObjectFolder a0) { Unsupported("InsertInstanceTo"); return default(ObjectInstanceItem); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectInstanceItem InsertInstanceTo(ObjectItem a0) { Unsupported("InsertInstanceTo"); return default(ObjectInstanceItem); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectInstanceItem InsertInstanceTo(ObjectsItem a0) { Unsupported("InsertInstanceTo"); return default(ObjectInstanceItem); } // https://help.iek-digital.ru/Help-web/objectitem.html
        public bool ResetDisableExecution() { ResetProp("DisableExecution"); return true; } // https://help.iek-digital.ru/Help-web/objectitem.html
        public bool ResetExecutePlace() { ResetProp("ExecutePlace"); return true; } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ObjectItem Ancestor { get { return GetProp<ObjectItem>("Ancestor"); } set { SetProp("Ancestor", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ControllerItem ControllerRef { get { return GetProp<ControllerItem>("ControllerRef"); } set { SetProp("ControllerRef", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ArchiveItem DataArchiveRef { get { return GetProp<ArchiveItem>("DataArchiveRef"); } set { SetProp("DataArchiveRef", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
        public bool DisableExecution { get { return GetProp<bool>("DisableExecution"); } set { SetProp("DisableExecution", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
        public EventsArchiveItem EventsArchiveRef { get { return GetProp<EventsArchiveItem>("EventsArchiveRef"); } set { SetProp("EventsArchiveRef", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ExecutePlaces ExecutePlace { get { return GetProp<ExecutePlaces>("ExecutePlace"); } set { SetProp("ExecutePlace", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
        public TaskItem TaskRef { get { return GetProp<TaskItem>("TaskRef"); } set { SetProp("TaskRef", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
        public ViewDeclarationInObjectItem WindowRef { get { return GetProp<ViewDeclarationInObjectItem>("WindowRef"); } set { SetProp("WindowRef", value); } } // https://help.iek-digital.ru/Help-web/objectitem.html
    }

    // https://help.iek-digital.ru/Help-web/objectortagbase.html
    public partial class ObjectOrTagBase : Item
    {
        public AlarmUsageItem AddAlarm(string a0 = null) { return AddChild<AlarmUsageItem>("AddAlarm", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public ProgramCsharpItem AddProgramCsharp(string a0 = null) { return AddChild<ProgramCsharpItem>("AddProgramCsharp", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public ProgramFBDItem AddProgramFBD(string a0 = null) { return AddChild<ProgramFBDItem>("AddProgramFBD", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public ProgramLDItem AddProgramLD(string a0 = null) { return AddChild<ProgramLDItem>("AddProgramLD", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public ProgramSFCItem AddProgramSFC(string a0 = null) { return AddChild<ProgramSFCItem>("AddProgramSFC", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public ProgramSTItem AddProgramST(string a0 = null) { return AddChild<ProgramSTItem>("AddProgramST", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public ReportItem AddReport(string a0 = null) { return AddChild<ReportItem>("AddReport", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public ViewDeclarationInObjectItem AddWindow(string a0 = null) { return AddChild<ViewDeclarationInObjectItem>("AddWindow", a0); } // https://help.iek-digital.ru/Help-web/objectortagbase.html
        public IEnumerable<ProgramParamItem> Parameters { get { return ChildrenOf<ProgramParamItem>(); } } // https://help.iek-digital.ru/Help-web/objectortagbase.html
    }

    // https://help.iek-digital.ru/Help-web/objectsitem.html
    public partial class ObjectsItem : CommonItem
    {
        public ObjectFolder AddFolder(string a0 = null) { return AddChild<ObjectFolder>("AddFolder", a0); } // https://help.iek-digital.ru/Help-web/objectsitem.html
        public ObjectItem AddObject(string a0 = null) { return AddChild<ObjectItem>("AddObject", a0); } // https://help.iek-digital.ru/Help-web/objectsitem.html
        public ObjectItem FindObject(string a0) { return FindDeep<ObjectItem>(a0); } // https://help.iek-digital.ru/Help-web/objectsitem.html
    }

    // https://help.iek-digital.ru/Help-web/programfbditem.html
    public partial class ProgramFBDItem : ProgramItem
    {
        public POUTypeUsageItem AddPOUTypeDeclarationToAlgoritm(POUTypeDeclarationItem a0, string a1, int a2, int a3) { Unsupported("AddPOUTypeDeclarationToAlgoritm"); return default(POUTypeUsageItem); } // https://help.iek-digital.ru/Help-web/programfbditem.html
        public POUTypeUsageItem AddPOUTypeDeclarationToAlgoritm(string a0, int a1, int a2) { return AddChild<POUTypeUsageItem>("AddPOUTypeDeclarationToAlgoritm", a0); } // https://help.iek-digital.ru/Help-web/programfbditem.html
        public IEnumerable<POUTypeUsageItem> FBsFromAlgoritm { get { return ChildrenOf<POUTypeUsageItem>(); } } // https://help.iek-digital.ru/Help-web/programfbditem.html
    }

    // https://help.iek-digital.ru/Help-web/programitem.html
    public partial class ProgramItem : Item
    {
        public LocalVarItem AddLocalVar(string a0 = null) { return AddChild<LocalVarItem>("AddLocalVar", a0); } // https://help.iek-digital.ru/Help-web/programitem.html
        public POUTypeDeclarationItem AddPOUTypeDeclaration(string a0 = null) { return AddChild<POUTypeDeclarationItem>("AddPOUTypeDeclaration", a0); } // https://help.iek-digital.ru/Help-web/programitem.html
        public ProgramParamItem AddProgramParam(string a0 = null) { return AddChild<ProgramParamItem>("AddProgramParam", a0); } // https://help.iek-digital.ru/Help-web/programitem.html
        public void ResetExecutePlace() { ResetProp("ExecutePlace"); } // https://help.iek-digital.ru/Help-web/programitem.html
        public void ResetExecutionMethod() { ResetProp("ExecutionMethod"); } // https://help.iek-digital.ru/Help-web/programitem.html
        public void ResetIsExternal() { ResetProp("IsExternal"); } // https://help.iek-digital.ru/Help-web/programitem.html
        public ExecutePlaces ExecutePlace { get { return GetProp<ExecutePlaces>("ExecutePlace"); } set { SetProp("ExecutePlace", value); } } // https://help.iek-digital.ru/Help-web/programitem.html
        public FBExecuteTypes ExecutionMethod { get { return GetProp<FBExecuteTypes>("ExecutionMethod"); } set { SetProp("ExecutionMethod", value); } } // https://help.iek-digital.ru/Help-web/programitem.html
        public IEnumerable<POUTypeDeclarationItem> FBPrograms { get { return ChildrenOf<POUTypeDeclarationItem>(); } } // https://help.iek-digital.ru/Help-web/programitem.html
        public bool IsExternal { get { return GetProp<bool>("IsExternal"); } set { SetProp("IsExternal", value); } } // https://help.iek-digital.ru/Help-web/programitem.html
        public IEnumerable<LocalVarItem> LocalVariables { get { return ChildrenOf<LocalVarItem>(); } } // https://help.iek-digital.ru/Help-web/programitem.html
        public IEnumerable<ProgramParamItem> Parameters { get { return ChildrenOf<ProgramParamItem>(); } } // https://help.iek-digital.ru/Help-web/programitem.html
    }

    // https://help.iek-digital.ru/Help-web/programlditem.html
    public partial class ProgramLDItem : ProgramItem
    {
    }

    // https://help.iek-digital.ru/Help-web/programparamitem.html
    public partial class ProgramParamItem : VariableItem
    {
        public void ResetAccess() { ResetProp("Access"); } // https://help.iek-digital.ru/Help-web/programparamitem.html
        public void ResetSaving() { ResetProp("Saving"); } // https://help.iek-digital.ru/Help-web/programparamitem.html
        public void ResetSwitching() { ResetProp("Switching"); } // https://help.iek-digital.ru/Help-web/programparamitem.html
        public AccessTypes Access { get { return GetProp<AccessTypes>("Access"); } set { SetProp("Access", value); } } // https://help.iek-digital.ru/Help-web/programparamitem.html
        public ModifierTypes Saving { get { return GetProp<ModifierTypes>("Saving"); } set { SetProp("Saving", value); } } // https://help.iek-digital.ru/Help-web/programparamitem.html
        public EdgeTypes Switching { get { return GetProp<EdgeTypes>("Switching"); } set { SetProp("Switching", value); } } // https://help.iek-digital.ru/Help-web/programparamitem.html
    }

    // https://help.iek-digital.ru/Help-web/programsfcitem.html
    public partial class ProgramSFCItem : ProgramItem
    {
    }

    // https://help.iek-digital.ru/Help-web/programstitem.html
    public partial class ProgramSTItem : ProgramItem
    {
        public string Text { get { return GetProp<string>("Text"); } set { SetProp("Text", value); } } // https://help.iek-digital.ru/Help-web/programstitem.html
    }

    // https://help.iek-digital.ru/Help-web/rootitem.html
    public partial class RootItem : Item
    {
        public LibrariesItem Libraries { get { return GetProp<LibrariesItem>("Libraries"); } set { SetProp("Libraries", value); } } // https://help.iek-digital.ru/Help-web/rootitem.html
        public ObjectsItem Objects { get { return GetProp<ObjectsItem>("Objects"); } set { SetProp("Objects", value); } } // https://help.iek-digital.ru/Help-web/rootitem.html
        public SystemItem System { get { return GetProp<SystemItem>("System"); } set { SetProp("System", value); } } // https://help.iek-digital.ru/Help-web/rootitem.html
    }

    // https://help.iek-digital.ru/Help-web/systemitem.html
    public partial class SystemItem : CommonItem
    {
        public ControllerItem AddARM(string a0 = null) { return AddChild<ControllerItem>("AddARM", a0); } // https://help.iek-digital.ru/Help-web/systemitem.html
        public ControllerItem AddController(string a0 = null) { return AddChild<ControllerItem>("AddController", a0); } // https://help.iek-digital.ru/Help-web/systemitem.html
        public ControllerItem AddServer(string a0 = null) { return AddChild<ControllerItem>("AddServer", a0); } // https://help.iek-digital.ru/Help-web/systemitem.html
        public ControllerItem FindController(string a0) { return FindDeep<ControllerItem>(a0); } // https://help.iek-digital.ru/Help-web/systemitem.html
        public IEnumerable<ControllerItem> Controllers { get { return ChildrenOf<ControllerItem>(); } } // https://help.iek-digital.ru/Help-web/systemitem.html
    }

    // https://help.iek-digital.ru/Help-web/taginstanceitem.html
    public partial class TagInstanceItem : ObjectOrTagInstanceItem
    {
        public void AddLink(ChannelItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void AddLink(TagInstanceItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void AddLink(TagItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void AddLink(VariableItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void Delete() { ResetProp(""); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void DeleteArchiveTemplateType() { ResetProp("ArchiveTemplateType"); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void DeleteScaleType() { ResetProp("ScaleType"); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void ResetHistorizing() { ResetProp("Historizing"); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public void TryAddLink(Item a0) { RecordLink("TryAddLink", a0); } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public TagItem Ancestor { get { return GetProp<TagItem>("Ancestor"); } set { SetProp("Ancestor", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public ArchiveTemplateItem ArchiveTemplate { get { return GetProp<ArchiveTemplateItem>("ArchiveTemplate"); } set { SetProp("ArchiveTemplate", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public string ArchiveTemplateType { get { return GetProp<string>("ArchiveTemplateType"); } set { SetProp("ArchiveTemplateType", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public Item DataSource { get { return GetProp<Item>("DataSource"); } set { SetProp("DataSource", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public bool DisableExecution { get { return GetProp<bool>("DisableExecution"); } set { SetProp("DisableExecution", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public bool Historizing { get { return GetProp<bool>("Historizing"); } set { SetProp("Historizing", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public ScaleItem Scale { get { return GetProp<ScaleItem>("Scale"); } set { SetProp("Scale", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
        public string ScaleType { get { return GetProp<string>("ScaleType"); } set { SetProp("ScaleType", value); } } // https://help.iek-digital.ru/Help-web/taginstanceitem.html
    }

    // https://help.iek-digital.ru/Help-web/taskitem.html
    public partial class TaskItem : Item
    {
        public void ResetIsUseForGlobalParams() { ResetProp("IsUseForGlobalParams"); } // https://help.iek-digital.ru/Help-web/taskitem.html
        public void ResetPeriod() { ResetProp("Period"); } // https://help.iek-digital.ru/Help-web/taskitem.html
        public void ResetPriority() { ResetProp("Priority"); } // https://help.iek-digital.ru/Help-web/taskitem.html
        public void ResetTranslatorType() { ResetProp("TranslatorType"); } // https://help.iek-digital.ru/Help-web/taskitem.html
        public bool IsUseForGlobalParams { get { return GetProp<bool>("IsUseForGlobalParams"); } set { SetProp("IsUseForGlobalParams", value); } } // https://help.iek-digital.ru/Help-web/taskitem.html
        public int Period { get { return GetProp<int>("Period"); } set { SetProp("Period", value); } } // https://help.iek-digital.ru/Help-web/taskitem.html
        public int Priority { get { return GetProp<int>("Priority"); } set { SetProp("Priority", value); } } // https://help.iek-digital.ru/Help-web/taskitem.html
        public TranslatorType TranslatorType { get { return GetProp<TranslatorType>("TranslatorType"); } set { SetProp("TranslatorType", value); } } // https://help.iek-digital.ru/Help-web/taskitem.html
    }

    // https://help.iek-digital.ru/Help-web/variableitem.html
    public partial class VariableItem : Item
    {
        public void AddLink(ChannelItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void AddLink(TagInstanceItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void AddLink(TagItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void AddLink(VariableItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void AddLink(ViewAccessParamItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void AddLink(ViewUsageParamItem a0) { RecordLink("AddLink", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void ChangeType(string a0) { SetProp("ValueType", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void DeleteArchiveTemplateType() { ResetProp("ArchiveTemplateType"); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void DeleteScaleType() { ResetProp("ScaleType"); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void ResetHistorizing() { ResetProp("Historizing"); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void ResetInitialValue() { ResetProp("InitialValue"); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void ResetValueType() { ResetProp("ValueType"); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public void TryAddLink(Item a0) { RecordLink("TryAddLink", a0); } // https://help.iek-digital.ru/Help-web/variableitem.html
        public ArchiveTemplateItem ArchiveTemplate { get { return GetProp<ArchiveTemplateItem>("ArchiveTemplate"); } set { SetProp("ArchiveTemplate", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
        public string ArchiveTemplateType { get { return GetProp<string>("ArchiveTemplateType"); } set { SetProp("ArchiveTemplateType", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
        public Item DataSource { get { return GetProp<Item>("DataSource"); } set { SetProp("DataSource", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
        public bool Historizing { get { return GetProp<bool>("Historizing"); } set { SetProp("Historizing", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
        public object InitialValue { get { return GetProp<object>("InitialValue"); } set { SetProp("InitialValue", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
        public ScaleItem Scale { get { return GetProp<ScaleItem>("Scale"); } set { SetProp("Scale", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
        public string ScaleType { get { return GetProp<string>("ScaleType"); } set { SetProp("ScaleType", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
        public string ValueType { get { return GetProp<string>("ValueType"); } set { SetProp("ValueType", value); } } // https://help.iek-digital.ru/Help-web/variableitem.html
    }

}
