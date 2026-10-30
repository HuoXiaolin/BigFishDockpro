"""Offline GitHub release selection and default settings checks."""
import copy,json,urllib.error
from unittest.mock import patch
from update_sources import DEFAULT_SOURCE,GITHUB_API,INSTALLER,REPOSITORY,parse_github_release
from update_service import fetch_manifest,version_tuple


def run(api,runtime,output,checks):
    normalized=api.normalize_features(dict(api.DEFAULT_CONFIG,update_source=''))
    assert normalized['update_source']==DEFAULT_SOURCE and normalized['desktop_middle_toggle']
    assert not api.normalize_features(dict(api.DEFAULT_CONFIG,desktop_middle_toggle=False))['desktop_middle_toggle']
    payload={'tag_name':'v9.0.0','html_url':REPOSITORY+'/releases/tag/v9.0.0','draft':False,'prerelease':False,
             'assets':[{'name':'BigFishDockpro.exe','state':'uploaded','size':500,'browser_download_url':REPOSITORY+'/releases/download/v9.0.0/BigFishDockpro.exe'},
                       {'name':INSTALLER,'state':'uploaded','size':1000,'browser_download_url':REPOSITORY+'/releases/download/v9.0.0/'+INSTALLER}]}
    result=parse_github_release(payload,'1.0.8',version_tuple)
    assert result['newer'] and result['installer_available'] and result['release_url'].endswith('/'+INSTALLER)
    assert not parse_github_release(payload,'9.0.0',version_tuple)['newer']
    for change in ({'draft':True},{'prerelease':True},{'html_url':'https://github.com/other/repo/releases/tag/v9.0.0'},{'tag_name':'v9.0.0-rc1'}):
        try:parse_github_release(dict(payload,**change),'1.0.8',version_tuple);raise AssertionError('Invalid release accepted')
        except ValueError:pass
    missing=parse_github_release(dict(payload,assets=[]),'1.0.8',version_tuple)
    assert not missing['installer_available'] and missing['release_url']==payload['html_url']
    wrong=copy.deepcopy(payload);wrong['assets'][1]['browser_download_url']='https://github.com/other/repo/releases/download/v9.0.0/'+INSTALLER
    assert not parse_github_release(wrong,'1.0.8',version_tuple)['installer_available']
    captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def geturl(self):return GITHUB_API
        def read(self,limit):return json.dumps(payload).encode('utf-8')
    class Opener:
        def open(self,request,timeout):captured.append(request.full_url);assert timeout==12;return Response()
    with patch('urllib.request.build_opener',return_value=Opener()):
        for source in (REPOSITORY,REPOSITORY+'/releases',DEFAULT_SOURCE,GITHUB_API):
            assert fetch_manifest(source,False)['installer_available'] and captured[-1]==GITHUB_API
    class Limited:
        def open(self,*args,**kwargs):raise urllib.error.HTTPError(GITHUB_API,403,'rate limit exceeded',{},None)
    with patch('urllib.request.build_opener',return_value=Limited()):
        try:fetch_manifest(DEFAULT_SOURCE,True);raise AssertionError('Rate limit was hidden')
        except ValueError as error:assert '访问受限' in str(error)
    # The existing custom manifest format still works.
    from update_service import parse_manifest
    assert parse_manifest({'product_id':'BigFishDockpro','version':'9.0.0','release_url':'https://example.com/releases'})['newer']
    from settings_dialog import SettingsDialog
    dialog=SettingsDialog(runtime.tray,api)
    try:
        dialog.reveal()
        assert dialog.fields['desktop_middle_toggle'].isChecked()==runtime.dock.cfg['desktop_middle_toggle']
        assert dialog.fields['update_source'].text()==DEFAULT_SOURCE
        dialog.tabs.nav.setCurrentRow(next(i for i in range(dialog.tabs.nav.count()) if dialog.tabs.nav.item(i).text()=='更新设置'))
        dialog.grab().save(str(output/'update-release-settings.png'))
    finally:dialog.reject();dialog.deleteLater()
    checks.append('release updates: middle-button default on and saved off preserved, old empty source migrated; own GitHub page/API aliases, formal v-tag comparison, installer preferred over portable, missing/foreign installer fallback, foreign/draft/prerelease rejection, rate-limit message, custom manifest compatibility; actual settings rendered; mocked HTTP only')
