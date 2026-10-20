# Видимые окна процесса и их текст (для --noUI: модальный диалог среды = зависание скрипта).
param([int]$ProcessId)
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class CdsWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@
$out = New-Object System.Collections.ArrayList
[CdsWin]::EnumWindows({ param($h, $l) $p = 0; [void][CdsWin]::GetWindowThreadProcessId($h, [ref]$p)
  if ($p -eq $ProcessId -and [CdsWin]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 512; [void][CdsWin]::GetWindowText($h, $sb, 512); [void]$out.Add("WIN: " + $sb.ToString())
    [CdsWin]::EnumChildWindows($h, { param($c, $x) $s2 = New-Object System.Text.StringBuilder 4000; [void][CdsWin]::GetWindowText($c, $s2, 4000)
      if ($s2.Length -gt 0) { [void]$out.Add($s2.ToString()) }; return $true }, [IntPtr]::Zero) | Out-Null }
  return $true }, [IntPtr]::Zero) | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$out -join "`n"
