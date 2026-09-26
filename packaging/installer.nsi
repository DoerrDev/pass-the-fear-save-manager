; Pass the Fear 存档管理器 安装脚本
; 由 packaging/build.py 调用，需要传入 VERSION / APP_DIR / ICON / OUTFILE

Unicode true
SetCompressor /SOLID lzma
ManifestDPIAware true

!define APP_NAME     "Pass the Fear 存档管理器"
!define APP_EXE      "PassTheFearSaveManager.exe"
!define APP_ID       "PassTheFearSaveManager"
!define UNINST_KEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

Name "${APP_NAME}"
OutFile "${OUTFILE}"
; 装在当前用户目录，不需要管理员权限
InstallDir "$LOCALAPPDATA\Programs\${APP_ID}"
InstallDirRegKey HKCU "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel user
BrandingText "${APP_NAME} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=2052 "FileDescription" "${APP_NAME} 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "风暴怕死队"

!include "MUI2.nsh"

!define MUI_ICON   "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${APP_NAME}"
!define MUI_WELCOMEPAGE_TEXT "Pass the Fear 的存档工具：命名存档、游戏内快捷键快速存档、一键回档并自动重启游戏。$\r$\n$\r$\n存档和设置保存在 %APPDATA%\${APP_ID}，重装或升级都不会丢失。$\r$\n$\r$\n点击「下一步」继续。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即运行 ${APP_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; 程序正在运行时提示先退出
!macro WAIT_APP_CLOSED
  check_running:
    nsExec::ExecToStack 'cmd /c tasklist /FI "IMAGENAME eq ${APP_EXE}" /NH | find /I "${APP_EXE}"'
    Pop $0
    Pop $1
    StrCmp $0 "0" 0 +3
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "${APP_NAME} 正在运行，请先退出它（包括系统托盘里的图标），再点「重试」。" /SD IDCANCEL IDRETRY check_running
      Abort
!macroend

Function .onInit
  !insertmacro WAIT_APP_CLOSED
FunctionEnd

Function un.onInit
  !insertmacro WAIT_APP_CLOSED
FunctionEnd

Section "Install"
  SetOutPath "$INSTDIR"
  ; 覆盖安装前清掉旧文件，避免残留旧版本的库
  RMDir /r "$INSTDIR\_internal"
  File /r "${APP_DIR}\*.*"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${APP_EXE}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "风暴怕死队"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"

  MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "是否同时删除所有存档和设置？$\r$\n（$APPDATA\${APP_ID}）$\r$\n$\r$\n选「否」会保留存档，以后重新安装还能继续用。" /SD IDNO IDNO keep_data
    RMDir /r "$APPDATA\${APP_ID}"
  keep_data:
SectionEnd
