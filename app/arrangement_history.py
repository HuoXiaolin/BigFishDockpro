"""Bounded session undo for references, never disk file operations."""
import copy
import json
_active=None


def record(cfg,before,after,title):
    if _active is not None and _active.cfg is cfg:
        _active.record(before,after,title)


class ArrangementHistory:
    def __init__(self,cfg,save,apply):
        global _active
        self.cfg,self.save,self.apply=cfg,save,apply
        self.entries=[];self.restoring=False;self.message='尚无可撤销的整理操作'
        _active=self

    def record(self,before,after,title):
        if self.restoring:return
        keys={k for k in before if k in after and before[k]!=after[k]}
        if not keys:return
        entry={'before':{k:copy.deepcopy(before[k]) for k in keys},'after':{k:copy.deepcopy(after[k]) for k in keys},'title':str(title)[:80]}
        entry['bytes']=len(json.dumps(entry,ensure_ascii=False).encode('utf-8'))
        if entry['bytes']>2*1024*1024:
            self.entries.clear();self.message='本次整理较大，未保留撤销记录';return
        self.entries.append(entry)
        while len(self.entries)>12 or sum(e['bytes'] for e in self.entries)>2*1024*1024:self.entries.pop(0)
        self.message='可撤销：'+entry['title']

    def undo(self):
        if not self.entries:self.message='尚无可撤销的整理操作';return False
        entry=self.entries[-1]
        if any(self.cfg.get(k)!=v for k,v in entry['after'].items()):
            self.message='相关内容已再次变化，不能覆盖新状态；请重新整理。';return False
        previous=copy.deepcopy(self.cfg);candidate=dict(self.cfg,**copy.deepcopy(entry['before']))
        if self.save(candidate) is False:self.message='保存失败，未撤销；请检查数据目录。';return False
        self.restoring=True
        try:
            self.cfg.update(candidate)
            try:self.apply(previous)
            except Exception:
                self.cfg.clear();self.cfg.update(previous);self.save(previous)
                try:self.apply(candidate)
                except Exception:pass
                self.message='撤销应用失败，已尝试恢复原状态。';return False
            self.entries.pop();self.message='已撤销：'+entry['title'];return True
        finally:self.restoring=False

    def close(self):
        global _active
        self.entries.clear()
        if _active is self:_active=None
