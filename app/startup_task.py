"""A least-privilege Windows logon task scoped to the current user SID."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

NS = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
DESCRIPTION = 'BigFishDockpro interactive logon'
SWITCH = '--scheduled-startup'
QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$service = New-Object -ComObject Schedule.Service
$service.Connect()
try {
    [xml]$task = $service.GetFolder('\').GetTask($env:BIGFISH_QUERY_TASK).Xml
    # Scheduler may export the logon trigger as DOMAIN\name even if registered by SID.
    foreach ($node in $task.SelectNodes("//*[local-name()='UserId']")) {
        if ($node.InnerText -and $node.InnerText -notmatch '^S-1-') {
            try {
                $account = [System.Security.Principal.NTAccount]::new($node.InnerText)
                $node.InnerText = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
            } catch {}
        }
    }
    [Console]::Write($task.OuterXml)
} catch {
    for ($cause = $_.Exception; $null -ne $cause; $cause = $cause.InnerException) {
        if ($cause.HResult -eq -2147024894) { exit 2 }
    }
    exit 1
}
"""


def user_sid():
    kernel = C.WinDLL('kernel32', use_last_error=True)
    advapi = C.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.LocalFree.argtypes = [C.c_void_p]
    advapi.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)]
    advapi.GetTokenInformation.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [C.c_void_p, C.POINTER(W.LPWSTR)]
    token = W.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, C.byref(token)):
        raise C.WinError(C.get_last_error())
    try:
        size = W.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, C.byref(size))
        buffer = C.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, C.byref(size)):
            raise C.WinError(C.get_last_error())
        result = W.LPWSTR()
        if not advapi.ConvertSidToStringSidW(C.cast(buffer, C.POINTER(C.c_void_p))[0], C.byref(result)):
            raise C.WinError(C.get_last_error())
        try:
            return result.value
        finally:
            kernel.LocalFree(result)
    finally:
        kernel.CloseHandle(token)


def task_xml(sid, argv, working_dir):
    root = ET.Element('Task', {'version':'1.2', 'xmlns':NS})
    def add(parent, tag, value=None, **attrs):
        child = ET.SubElement(parent, tag, attrs)
        child.text = value
        return child
    add(add(root, 'RegistrationInfo'), 'Description', DESCRIPTION)
    trigger = add(add(root, 'Triggers'), 'LogonTrigger')
    add(trigger, 'Enabled', 'true');add(trigger, 'UserId', sid)
    principal = add(add(root, 'Principals'), 'Principal', id='DockUser')
    add(principal, 'UserId', sid);add(principal, 'LogonType', 'InteractiveToken')
    add(principal, 'RunLevel', 'LeastPrivilege')
    settings = add(root, 'Settings')
    for tag,value in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),
                      ('StopIfGoingOnBatteries','false'),('ExecutionTimeLimit','PT0S'),('Priority','4')]:
        add(settings,tag,value)
    action = add(add(root, 'Actions', Context='DockUser'), 'Exec')
    add(action,'Command',argv[0]);add(action,'Arguments',subprocess.list2cmdline([*argv[1:],SWITCH]))
    add(action,'WorkingDirectory',working_dir)
    return ET.tostring(root, encoding='utf-16', xml_declaration=True)


def inspect_xml(data, sid):
    root = ET.fromstring(data)
    scope = {'t':NS}
    def get(path, default=''):
        return root.findtext('/'.join('t:'+part for part in path.split('/')), default, scope)
    if get('RegistrationInfo/Description') != DESCRIPTION or get('Principals/Principal/UserId') != sid:
        raise OSError('任务名称已被其他应用使用。')
    actions = root.find('t:Actions', scope);triggers = root.find('t:Triggers', scope)
    valid = (actions is not None and len(actions)==1 and triggers is not None and len(triggers)==1
             and get('Triggers/LogonTrigger/UserId')==sid and get('Triggers/LogonTrigger/Delay','PT0S')=='PT0S'
             and get('Principals/Principal/LogonType')=='InteractiveToken'
             and get('Principals/Principal/RunLevel','LeastPrivilege')=='LeastPrivilege'
             and get('Settings/Priority')=='4' and get('Settings/ExecutionTimeLimit')=='PT0S'
             and get('Settings/DisallowStartIfOnBatteries')=='false' and get('Settings/StopIfGoingOnBatteries')=='false')
    enabled = get('Settings/Enabled','true')=='true' and get('Triggers/LogonTrigger/Enabled','true')=='true'
    program = get('Actions/Exec/Command')
    arguments = get('Actions/Exec/Arguments')
    return dict(program=program, command=subprocess.list2cmdline([program])+' '+arguments, enabled=enabled,
                valid=valid, directory=get('Actions/Exec/WorkingDirectory'), xml=data)


class LogonTask:
    def __init__(self):
        self.sid = user_sid()
        if not re.fullmatch(r'S-1-(?:[0-9]+-)*[0-9]+', self.sid):raise OSError('用户 SID 无效。')
        self.name = r'\BigFishDockpro-' + self.sid
        self.exe = str(Path(os.environ['SystemRoot'])/'System32'/'schtasks.exe')

    def run(self,*args):
        return subprocess.run([self.exe,*args], stdin=subprocess.DEVNULL, capture_output=True,
                              creationflags=subprocess.CREATE_NO_WINDOW, timeout=3)

    def read(self):
        # schtasks /Query /XML can print ANSI while declaring UTF-16, and
        # loses paths outside the system code page. Read the COM XML losslessly.
        powershell = Path(self.exe).parent/'WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-Command',QUERY],
                                env=dict(os.environ,BIGFISH_QUERY_TASK=self.name), stdin=subprocess.DEVNULL,
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
        if result.returncode==2:return None
        if result.returncode:raise OSError('Windows 任务计划程序未能读取登录任务。')
        return inspect_xml(result.stdout.decode('utf-8-sig').encode('utf-16'),self.sid)

    def write(self,data):
        with tempfile.TemporaryDirectory(prefix='bigfish-logon-') as directory:
            path = Path(directory)/'startup.xml';path.write_bytes(data)
            result = self.run('/Create','/TN',self.name,'/XML',str(path),'/F')
        if result.returncode:raise OSError(f'Windows 任务计划程序拒绝注册（{result.returncode}）。')

    def remove(self):
        if self.run('/Delete','/TN',self.name,'/F').returncode:raise OSError('无法删除本应用的登录任务。')
