"""Bounded arrangement history and local command-search regression checks."""
import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch


def run(api,runtime,main,app,output,checks):
    import arrangement_history
    from arrangement_history import ArrangementHistory
    from command_search import matches,SearchDialog
    from PyQt5.QtCore import Qt
    from ui_test_events import Events as QTest
    from PyQt5 import sip
    active=arrangement_history._active
    try:
        cfg={'items':[{'path':'before'}],'sticky_notes':[{'id':'note','text':'keep original text'}]}
        save=MagicMock(return_value=True);apply=MagicMock()
        history=ArrangementHistory(cfg,save,apply)
        before=copy.deepcopy(cfg['items']);cfg['items']=[{'path':'after'}]
        history.record({'items':before},{'items':cfg['items']},'reorder')
        cfg['sticky_notes'][0]['text']='new text written after arrangement'
        assert history.undo() and cfg['items']==before and cfg['sticky_notes'][0]['text']=='new text written after arrangement'
        assert apply.call_count==1 and not history.entries
        for index in range(20):
            previous=copy.deepcopy(cfg['items']);cfg['items']=[{'path':str(index)}]
            history.record({'items':previous},{'items':cfg['items']},'step')
        assert len(history.entries)==12 and sum(row['bytes'] for row in history.entries)<=2*1024*1024
        snapshot=copy.deepcopy(cfg);count=len(history.entries);save.return_value=False
        assert not history.undo() and cfg==snapshot and len(history.entries)==count
        save.return_value=True;cfg['items']=[{'path':'external change'}];save.reset_mock()
        assert not history.undo() and not save.called and cfg['items']==[{'path':'external change'}]
        history.record({'items':[]},{'items':[{'path':'x'*(2*1024*1024+1)}]},'oversize')
        assert not history.entries
        history.close()
    finally:arrangement_history._active=active
    checks.append('arrangement undo: saved success, failed write leaves model/history unchanged, conflict refuses overwrite, note text untouched, 12-entry/2-MiB limits')

    cfg=runtime.dock.cfg;snapshot=copy.deepcopy(cfg)
    service=runtime.productivity
    history_entries=copy.deepcopy(service.history.entries);history_message=service.history.message
    with tempfile.TemporaryDirectory(prefix='search-review-',dir=str(output)) as temporary:
        root=Path(temporary);program=root/'Example.exe';program.write_bytes(b'fixture only');document=root/'Meeting.txt';document.write_text('original document',encoding='utf-8')
        apps=[{'path':str(program),'name':'浏览器 · 工作','arguments':'--profile work'},
              {'path':str(program),'name':'浏览器 · 个人','arguments':'--profile personal'}]
        files=[{'path':str(document),'name':'会议记录','panel':'documents','source':'manual'}]
        notes=[{'id':'review-note','title':'本周计划','text':'准备发布说明和版本记录'}]
        settings=[{'key':'icon_size','title':'Dock 图标大小','page':'外观设置','options':'小 中 大'},
                  {'key':'@references','title':'失效入口检查','page':'组件与整理','options':''}]
        search_cfg=dict(cfg,items=apps+[dict(apps[0])],desktop_entries=files+files)
        found,total=matches(search_cfg,notes,settings,'','apps');assert total==2 and len(found)==2
        found,total=matches(search_cfg,notes,settings,'profile work','apps');assert total==1 and found[0]['payload']['arguments']=='--profile work'
        found,total=matches(search_cfg,notes,settings,str(document),'files');assert total==1
        found,total=matches(search_cfg,notes,settings,'发布说明','notes');assert total==1 and found[0]['payload']=='review-note'
        found,total=matches(search_cfg,notes,settings,'大小','settings');assert total==1 and found[0]['payload']=='icon_size'
        urls=dict(search_cfg,items=[{'name':'A','path':'https://example.com/Case'},{'name':'B','path':'https://example.com/case'}])
        assert matches(urls,[],[],'','apps')[1]==2
        many=[{'id':str(i),'title':'N '+str(i),'text':'t'} for i in range(150)]
        found,total=matches({},many,[],'','notes',limit=100);assert total==150 and len(found)==100
        checks.append('local search: full parameterized launch identity, URL path casing, saved file path, note body and setting labels/options; scope filters, dedup and 100-result cap')

        try:
            with patch.object(runtime.layout,'pending',False),patch.object(runtime.notes,'flush',return_value=True):
                candidate=dict(cfg,items=apps,desktop_entries=files)
                with patch.object(api,'save_config',return_value=False):
                    assert not service.commit(candidate,'测试保存') and cfg==snapshot
                # Exercise the actual runtime apply path, not just the history helper.
                assert service.commit(candidate,'测试整理')
                assert cfg['items']==apps and document.read_text(encoding='utf-8')=='original document'
                with patch.object(runtime.tray,'showMessage'):
                    assert service.undo()
                assert cfg['items']==snapshot['items'] and document.read_text(encoding='utf-8')=='original document'
            # Populate existing-reference fixtures without applying them to the real desktop.
            cfg['items']=apps;cfg['desktop_entries']=files
            settings_window=SimpleNamespace(search_targets=lambda:settings,focus_setting=MagicMock())
            with patch.object(runtime.notes,'rows',return_value=notes):
                dialog=SearchDialog(runtime)
                with patch.object(dialog,'settings_targets',return_value=settings):
                    dialog.show();dialog.refresh();app.processEvents()
                    assert len(dialog.results)==6
                    dialog.grab().save(str(Path(output)/'review-unified-search.png'))
                    dialog.scope.setCurrentIndex(dialog.scope.findData('apps'));dialog.timer.stop();dialog.query.setText('工作');dialog.timer.stop();dialog.refresh()
                    assert len(dialog.results)==1
                    with patch.object(runtime.dock,'launch') as launch:
                        dialog.activate();assert launch.call_args.kwargs['source']=='dock_launch' and launch.call_args.args[0]['arguments']=='--profile work'
                    app.processEvents()
                for scope,query,expected in [('files','会议','file_open'),('notes','本周','review-note'),('settings','大小','icon_size')]:
                    dialog=SearchDialog(runtime)
                    with patch.object(dialog,'settings_targets',return_value=settings),patch.object(runtime.tray,'settings_dialog',settings_window,create=True):
                        dialog.scope.setCurrentIndex(dialog.scope.findData(scope));dialog.query.setText(query);dialog.timer.stop();dialog.refresh()
                        with patch.object(runtime.dock,'launch') as launch,patch.object(runtime.notes,'open') as open_note,patch.object(runtime,'show_settings'):
                            dialog.activate()
                            if scope=='files':assert launch.call_args.kwargs['source']==expected
                            elif scope=='notes':open_note.assert_called_once_with(expected)
                            else:settings_window.focus_setting.assert_called_once_with(expected)
                        app.processEvents()
                dialog=SearchDialog(runtime)
                with patch.object(dialog,'settings_targets',return_value=settings):
                    dialog.show();dialog.refresh();QTest.keyClick(dialog,Qt.Key_Escape);app.processEvents()
                    assert sip.isdeleted(dialog) or not dialog.isVisible()
            checks.append('productivity runtime and search UI: failed save does not apply; arrange/undo preserve original fixture file, real search render and app/file/note/settings activation routing, Escape closes')
        finally:
            previous=copy.deepcopy(cfg);cfg.clear();cfg.update(snapshot)
            api.save_config(cfg)
            try:service.apply(previous)
            finally:
                service.history.entries=history_entries;service.history.message=history_message
