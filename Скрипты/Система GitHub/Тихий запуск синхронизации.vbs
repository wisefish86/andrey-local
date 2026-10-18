' Starts PowerShell script hidden.
Option Explicit
Dim shell, command, scriptPath, exitCode
If WScript.Arguments.Count <> 1 Then WScript.Quit 2
scriptPath = WScript.Arguments(0)
Set shell = CreateObject("WScript.Shell")
command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File " & Chr(34) & scriptPath & Chr(34)
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
