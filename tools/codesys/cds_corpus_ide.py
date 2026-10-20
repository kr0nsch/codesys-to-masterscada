# -*- coding: utf-8 -*-
"""Скрипт CODESYS 3.5.17.30 (IronPython 2.7, --noUI --runscript): корпус УДР-1 → проект → сборка →
экспорт PLCopen XML → стенды в Control Win → чтение трасс.

Задание — JSON по пути из переменной окружения CDS_JOB. Запускает tools/codesys/corpus.py (хост держит
блокировку рантайма). Шаги:
1. проект с CODESYS Control Win V3 (4096 / 0000 0001 / 3.5.17.30);
2. DUT, GVL, POU на ST и ООП — текстовым API; графика и IL — import_xml рукописного TC6;
3. задачи корпуса → сборка → export_xml приложения (source.cds.xml);
4. задачи корпуса удаляются, добавляются стенды PRG_Stand_* в задаче StandTask → пересборка;
5. вход в рантайм, старт, ожидание флагов xDone стендов, чтение массивов read_values, стоп, выход.
"""

from __future__ import absolute_import, print_function, unicode_literals

import io
import json
import os
import time
import traceback

import scriptengine as SE

JOB_PATH = os.environ.get("CDS_JOB")
JOB = json.load(io.open(JOB_PATH, encoding="utf-8"))
LOG = io.open(JOB["log"], "w", encoding="utf-8")
RESULT = {"steps": [], "ok": False}


def log(msg):
    LOG.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    LOG.flush()


def text(x):
    try:
        return unicode(x)  # noqa: F821
    except Exception:
        return str(x)


def messages():
    out = []
    for cat in system.get_message_categories():  # noqa: F821
        for m in system.get_message_objects(cat):  # noqa: F821
            try:
                sev = text(m.severity)
            except Exception:
                sev = "?"
            out.append({"severity": sev, "text": text(m.text), "object": text(getattr(m, "object", ""))})
    return out


def clear_messages():
    try:
        for cat in system.get_message_categories():  # noqa: F821
            system.clear_messages(cat)  # noqa: F821
    except Exception:
        pass


def children(obj):
    try:
        return list(obj.get_children(False))
    except Exception:
        return []


def find(obj, name):
    for c in children(obj):
        try:
            if text(c.get_name()).lower() == name.lower():
                return c
        except Exception:
            pass
    return None


def set_decl(obj, decl):
    obj.textual_declaration.replace(decl)


def set_impl(obj, impl):
    obj.textual_implementation.replace(impl)


def dut_kind(kind):
    return {
        "struct": DutType.Structure,
        "union": DutType.Union,
        "enum": DutType.Enumeration,  # noqa: F821
        "alias": DutType.Alias,
    }[kind]


def create_text_objects(app):
    created = []
    for name in sorted(JOB["duts"]):
        kind, decl = JOB["duts"][name]
        if kind == "alias":
            d = app.create_dut(name, DutType.Alias, "INT")  # noqa: F821
        else:
            d = app.create_dut(name, dut_kind(kind))
        set_decl(d, decl)
        created.append(name)
    for name in sorted(JOB["gvls"]):
        g = app.create_gvl(name)
        set_decl(g, JOB["gvls"][name])
        created.append(name)
    for itf in JOB.get("interfaces", []):
        i = app.create_interface(itf["name"])
        set_decl(i, "INTERFACE %s\n" % itf["name"])
        for mname, mdecl in itf["methods"]:
            m = i.create_method(mname)
            set_decl(m, mdecl)
        for pname, pdecl in itf["properties"]:
            pr = i.create_property(pname, "INT")
            set_decl(pr, pdecl)
            for acc in children(pr):
                if text(acc.get_name()).lower() == "set":
                    acc.remove()
        created.append(itf["name"])
    for name, kind, decl, body in JOB["st_pous"]:
        if kind == "function":
            rt = decl.split("FUNCTION", 1)[1].split(":", 1)[1].split("\n", 1)[0].strip()
            p = app.create_pou(name, PouType.Function, return_type=rt)  # noqa: F821
        elif kind == "functionBlock":
            p = app.create_pou(name, PouType.FunctionBlock)  # noqa: F821
        else:
            p = app.create_pou(name, PouType.Program)  # noqa: F821
        set_decl(p, decl)
        set_impl(p, body)
        created.append(name)
    for fb in JOB.get("oop", []):
        p = app.create_pou(fb["name"], PouType.FunctionBlock)  # noqa: F821
        set_decl(p, fb["decl"])
        set_impl(p, fb["body"])
        for mname, mdecl, mbody in fb["methods"]:
            m = p.create_method(mname)
            set_decl(m, mdecl)
            set_impl(m, mbody)
        for pname, pdecl, get_body, set_body in fb["properties"]:
            pr = p.create_property(pname, "INT")
            set_decl(pr, pdecl)
            for acc in children(pr):
                an = text(acc.get_name()).lower()
                if an == "get":
                    set_impl(acc, get_body)
                elif an == "set":
                    if set_body is None:
                        acc.remove()
                    else:
                        set_impl(acc, set_body)
        created.append(fb["name"])
    return created


def create_tasks(app, tasks):
    tc = None
    for c in children(app):
        if getattr(c, "is_task_configuration", False):
            tc = c
    if tc is None:
        tc = app.create_task_configuration()
    out = []
    for t in tasks:
        task = tc.create_task(t["name"])
        info = {"name": t["name"]}
        try:
            task.priority = text(t.get("priority", 1))
        except Exception as exc:
            info["priority_error"] = text(exc)
        kind = t.get("kind", "Cyclic")
        if kind == "Cyclic":
            task.interval = text(t["interval"]).replace("T#", "").replace("MS", "").replace("ms", "")
            try:
                task.interval_unit = "ms"
            except Exception:
                pass
        else:
            try:
                task.kind_of_task = getattr(KindOfTask, kind)  # noqa: F821
                info["kind_set"] = kind
            except Exception as exc:
                info["kind_error"] = text(exc)
            if t.get("event"):
                try:
                    task.event = t["event"]
                except Exception as exc:
                    info["event_error"] = text(exc)
        for pn in t["pous"]:
            task.pous.add(pn)
        out.append(info)
    return tc, out


def build(app):
    clear_messages()
    app.build()
    msgs = messages()
    errs = [m for m in msgs if m["severity"] in ("Error", "FatalError")]
    return msgs, errs


def read_credentials(path):
    data = json.load(io.open(path, encoding="utf-8"))
    return data.get("user") or data.get("username"), data.get("password")


def online_run(proj, app, dev):
    rt = JOB["runtime"]
    online = SE.online
    gws = list(online.gateways)
    if not gws:
        online.gateways.add_new_gateway("Gateway-1", {"IP-Address": "localhost", "Port": 1217})
        gws = list(online.gateways)
    dev.set_gateway_and_ip_address(gws[0], rt.get("device_address", "127.0.0.1"))
    user, pw = read_credentials(rt["credentials"])
    online.set_default_credentials(user, pw)
    oa = online.create_online_application(app)
    oa.login(OnlineChangeOption.Never, True)  # noqa: F821
    log("вход выполнен, загрузка приложения")
    oa.start()
    started = time.time()
    flags = ["%s.xDone" % s["name"] for s in JOB["stands"]]
    done = False
    while time.time() - started < float(rt.get("timeout_s", 120)):
        system.delay(500)  # noqa: F821
        vals = [text(v) for v in oa.read_values(flags)]
        if all(v.upper().endswith("TRUE") for v in vals):
            done = True
            break
    RESULT["run_seconds"] = round(time.time() - started, 1)
    RESULT["run_done"] = done
    traces = {}
    for s in JOB["stands"]:
        arrays = {}
        for arr in s["arrays"]:
            exprs = ["%s.%s[%d]" % (s["name"], arr["name"], i) for i in range(arr["n"])]
            vals = []
            for k in range(0, len(exprs), 200):
                vals.extend([text(v) for v in oa.read_values(exprs[k : k + 200])])
            arrays[arr["name"]] = vals
        traces[s["name"]] = arrays
    RESULT["traces"] = traces
    oa.stop()
    oa.logout()
    log("стенды прочитаны, выход из рантайма")


def main():
    proj = None
    try:
        path = JOB["project"]
        if os.path.exists(path):
            os.remove(path)
        log("старт: создание проекта")
        proj = projects.create(path, True)  # noqa: F821
        log("проект создан")
        dev = JOB["device"]
        proj.add("Device", DeviceID(int(dev["type"]), dev["id"], dev["version"]))  # noqa: F821
        log("устройство добавлено")
        app = proj.active_application
        libs = []
        for c in children(app):
            if getattr(c, "is_libman", False):
                for lib in JOB.get("libraries", []):
                    # плейсхолдер разрешает профиль CODESYS (Standard 3.5.17.0 для SP17P3); доступ без пространства имён
                    try:
                        c.add_placeholder(lib["placeholder"], lib["target"])
                        libs.append("#%s -> %s" % (lib["placeholder"], lib["target"]))
                    except Exception as exc:
                        libs.append("#%s: %s" % (lib["placeholder"], text(exc)))
                try:
                    RESULT["library_refs"] = [text(getattr(r, "name", r)) for r in c.references]
                except Exception as exc:
                    RESULT["library_refs"] = "error: %s" % text(exc)
        RESULT["libraries"] = libs
        log("библиотеки: %d" % len(libs))
        RESULT["created"] = create_text_objects(app)
        log("текстовые объекты: %d" % len(RESULT["created"]))
        imports = {}
        for pname, xml_path in JOB["xml"]:
            try:
                app.import_xml(None, xml_path)
                imports[pname] = "ok" if find(app, pname) is not None else "not created"
            except Exception as exc:
                imports[pname] = "error: %s" % text(exc)
        RESULT["import"] = imports
        RESULT["objects_after_import"] = sorted(text(c.get_name()) for c in children(app))
        tc, tinfo = create_tasks(app, JOB["tasks"])
        RESULT["tasks"] = tinfo
        msgs, errs = build(app)
        RESULT["build"] = {"messages": msgs, "errors": len(errs)}
        log("сборка корпуса: ошибок %d" % len(errs))
        proj.export_xml(
            [app], path=JOB["export"], recursive=True, export_folder_structure=True, declarations_as_plaintext=True
        )
        RESULT["export"] = JOB["export"]
        each = {}
        for name in JOB.get("export_each", []):
            obj = find(app, name)
            if obj is None:
                each[name] = "not found"
                continue
            try:
                out = os.path.join(JOB["export_dir"], "form_%s.xml" % name)
                proj.export_xml(
                    [obj], path=out, recursive=True, export_folder_structure=False, declarations_as_plaintext=True
                )
                each[name] = "ok"
            except Exception as exc:
                each[name] = "error: %s" % text(exc)
        RESULT["export_each"] = each
        if JOB.get("stands"):
            for task in children(tc):
                task.remove()
            for s in JOB["stands"]:
                p = app.create_pou(s["name"], PouType.Program)  # noqa: F821
                set_decl(p, s["decl"])
                set_impl(p, s["body"])
            create_tasks(
                app,
                [
                    {
                        "name": "StandTask",
                        "kind": "Cyclic",
                        "interval": JOB["stand_ms"],
                        "priority": 1,
                        "pous": [s["name"] for s in JOB["stands"]],
                    }
                ],
            )
            msgs2, errs2 = build(app)
            RESULT["stand_build"] = {
                "messages": [m for m in msgs2 if m["severity"] in ("Error", "FatalError", "Warning")],
                "errors": len(errs2),
            }
            log("сборка стендов: ошибок %d" % len(errs2))
            if not errs2 and JOB.get("run"):
                online_run(proj, app, next(o for o in proj.get_children(False) if o.is_device))
        RESULT["ok"] = True
    except Exception:
        RESULT["error"] = traceback.format_exc()
        log(RESULT["error"])
    finally:
        try:
            if proj is not None:
                proj.close()
        except Exception:
            pass
        with io.open(JOB["result"], "w", encoding="utf-8") as f:
            f.write(json.dumps(RESULT, ensure_ascii=False, indent=1))
        LOG.close()


main()
