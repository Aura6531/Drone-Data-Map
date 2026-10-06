; ============================================================
;  无人机巡查数据地图 —— Inno Setup 安装脚本
;
;  编译方式（任选其一）：
;    1) 装了 Inno Setup 6 后，双击本文件，按 F9（Compile）
;    2) 命令行： "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\UAVMap.iss
;    3) 直接用仓库里的 packaging\build_installer.ps1（会先跑 PyInstaller 再编译）
;
;  产物： packaging\installer\无人机巡查数据地图_安装程序.exe
;
;  设计要点（与用户确认过的方案一致）：
;    * 默认装到 %LOCALAPPDATA%\无人机巡查数据地图 —— 数据放在程序目录内，
;      所以安装目录必须可写，绝不能默认 Program Files
;    * 结束页让用户填天地图 key，写进 <安装目录>\tianditu_key.txt（存盘即生效）
;    * 开始菜单 + 可选桌面快捷方式；不开机自启
;    * 卸载保留 Data\ 与 Project\（用户数据不能删）
;    * 只带 ffmpeg.exe（ffprobe 代码里没用到），许可文本一起带上
; ============================================================

#define AppName "无人机巡查数据地图"
#define AppVersion "1.0.0"
#define AppExe "UAVMap.exe"
#define PayloadDir "..\packaging\dist\UAVMap"

[Setup]
AppId={{8E1B7A54-2C4D-4F1B-9A3E-7D5C0B6A1F22}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=无人机巡查数据地图
DefaultDirName={localappdata}\无人机巡查数据地图
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes
OutputDir=..\packaging\installer
OutputBaseFilename=无人机巡查数据地图_安装程序
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=UAVMap.ico
LicenseFile=
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
; 程序本体（PyInstaller 目录版整份）
Source: "{#PayloadDir}\{#AppExe}";                     DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\_internal\*";                   DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; 图标 + 说明书 + 许可（放安装根目录，用户一眼能看到）
Source: "UAVMap.ico";                                  DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\使用说明.md";                          DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\天地图key申请说明.md";                  DestDir: "{app}\说明"; Flags: ignoreversion
Source: "..\packaging\payload\ffmpeg\LICENSE";         DestDir: "{app}\说明"; DestName: "ffmpeg-LICENSE.txt"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\packaging\payload\ffmpeg\README.txt";      DestDir: "{app}\说明"; DestName: "ffmpeg-README.txt"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\UAVMap.ico"
Name: "{group}\使用说明";                 Filename: "{app}\使用说明.md"
Name: "{group}\卸载 {#AppName}";           Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\UAVMap.ico"; Tasks: desktopicon

[Run]
; 装完可选立刻启动（勾了就带托盘跑起来）
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只清运行期缓存；Data\ 与 Project\ 是用户数据，**故意不删**
Type: filesandordirs; Name: "{app}\tile_cache"
Type: filesandordirs; Name: "{app}\video_proxy"
Type: filesandordirs; Name: "{app}\report_cache"
Type: filesandordirs; Name: "{app}\geocode_cache"
Type: files;          Name: "{app}\运行日志.txt"

[Code]
var
  KeyPage: TInputQueryWizardPage;
  LinkLabel: TNewStaticText;

{ 结束页：填天地图 key + 申请指引 }
procedure InitializeWizard;
begin
  KeyPage := CreateInputQueryPage(wpSelectTasks,
    '天地图 key（可跳过）',
    '底图与地名搜索需要一串属于你自己的天地图 key（免费，约 2 分钟申请）',
    '申请步骤：① 打开下方网址并注册/登录 ② 创建应用，应用类型选「浏览器端」 ③ 把生成的 32 位 tk 粘到下面。' + #13#10 +
    '没填也能用：底图会自动退回 OpenStreetMap，只是地名搜索不可用；以后把 tk 放进程序目录的 tianditu_key.txt 也一样（存盘即生效，不用重启）。');

  KeyPage.Add('天地图 key（tk，32 位）：', False);

  LinkLabel := TNewStaticText.Create(KeyPage);
  LinkLabel.Parent := KeyPage.Surface;
  LinkLabel.Caption := '申请地址：https://console.tianditu.gov.cn/api/key';
  LinkLabel.Left := 0;
  LinkLabel.Top := KeyPage.Surface.Height - 26;
  LinkLabel.Width := KeyPage.Surface.Width;
  LinkLabel.Font.Color := clBlue;
end;

{ 把用户填的 tk 写进安装目录（无 BOM UTF-8；留空则不建文件） }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Key: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  Key := Trim(KeyPage.Values[0]);

  if Key = '' then
    Exit;

  if not SaveStringToFile(ExpandConstant('{app}\tianditu_key.txt'), Key + #13#10, False) then
    MsgBox('天地图 key 写入失败，请手动把 tk 粘贴到：' + #13#10 +
           ExpandConstant('{app}\tianditu_key.txt'), mbInformation, MB_OK);
end;

{ 长度不像 tk 时给个提醒，但不阻止继续（装完可能还没网，联网校验只会卡住人） }
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Key: String;
begin
  Result := True;

  if (KeyPage <> nil) and (CurPageID = KeyPage.ID) then
  begin
    Key := Trim(KeyPage.Values[0]);

    if (Key <> '') and (Length(Key) <> 32) then
    begin
      if MsgBox('这看起来不是天地图的 tk（通常是 32 位数字/字母）。' + #13#10 +
                '可以留空跳过，之后再放进 tianditu_key.txt。' + #13#10#13#10 +
                '要继续吗？', mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
    end;
  end;
end;
