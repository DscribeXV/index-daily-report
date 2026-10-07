Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = fso.BuildPath(scriptDir, "启动分析.bat")

ret = WshShell.Run("cmd /c """ & batPath & """", 0, True)

If ret <> 0 Then
    MsgBox "脚本运行失败，错误码 " & ret, vbExclamation, "今日指数分析"
End If