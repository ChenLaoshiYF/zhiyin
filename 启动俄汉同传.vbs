Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set ws = CreateObject("WScript.Shell")
ws.Run """" & dir & "\.venv\Scripts\pythonw.exe"" """ & dir & "\launcher.pyw""", 0, False
