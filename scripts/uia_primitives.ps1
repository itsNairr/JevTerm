# UI Automation Primitives for JevTerm
# Provides 10 foundational commands for Windows UI Automation via System.Windows.Automation and user32.dll

$code = @'
using System;
using System.Text;
using System.Threading;
using System.Diagnostics;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;

public class UIAutomationHelper {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr OpenDesktop(string lpszDesktop, uint dwFlags, bool fInherit, uint dwDesiredAccess);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetThreadDesktop(IntPtr hDesktop);

    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern uint SendInput(uint nInputs, [MarshalAs(UnmanagedType.LPArray), In] INPUT[] pInputs, int cbSize);

    public const uint DESKTOP_ALL = 0x01FF;
    public const uint INPUT_MOUSE = 0;
    public const uint INPUT_KEYBOARD = 1;

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    public const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
    public const uint MOUSEEVENTF_RIGHTUP = 0x0010;
    public const uint MOUSEEVENTF_WHEEL = 0x0800;

    public const uint KEYEVENTF_KEYUP = 0x0002;
    public const uint KEYEVENTF_UNICODE = 0x0004;

    public const uint WM_CLOSE = 0x0010;
    public const int SW_RESTORE = 9;

    [StructLayout(LayoutKind.Explicit)]
    public struct INPUT {
        [FieldOffset(0)]
        public uint type;
        [FieldOffset(8)]
        public MOUSEINPUT mi;
        [FieldOffset(8)]
        public KEYBDINPUT ki;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    private static void AttachToDefaultDesktop() {
        try {
            IntPtr hDesktop = OpenDesktop("Default", 0, false, DESKTOP_ALL);
            if (hDesktop != IntPtr.Zero) {
                SetThreadDesktop(hDesktop);
            }
        } catch {}
    }

    private static string EscapeJson(string s) {
        if (string.IsNullOrEmpty(s)) return "";
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "").Replace("\n", " ");
    }

    // 1. Get-OpenWindows
    public static string GetWindowsJson() {
        string result = "[]";
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                AutomationElement root = AutomationElement.RootElement;
                if (root == null) return;

                AutomationElementCollection windows = root.FindAll(TreeScope.Children, Condition.TrueCondition);
                List<string> items = new List<string>();

                foreach (AutomationElement w in windows) {
                    try {
                        string name = w.Current.Name;
                        bool offscreen = w.Current.IsOffscreen;
                        var rect = w.Current.BoundingRectangle;
                        int pid = w.Current.ProcessId;

                        if (!string.IsNullOrWhiteSpace(name) && !offscreen && rect.Width > 0 && rect.Height > 0) {
                            string procName = "unknown";
                            try {
                                procName = Process.GetProcessById(pid).ProcessName;
                            } catch {}

                            string item = string.Format(
                                "{{\"name\":\"{0}\",\"process\":\"{1}\",\"pid\":{2},\"bbox\":{{\"x\":{3},\"y\":{4},\"width\":{5},\"height\":{6}}}}}",
                                EscapeJson(name), EscapeJson(procName), pid, (int)rect.X, (int)rect.Y, (int)rect.Width, (int)rect.Height
                            );
                            items.Add(item);
                        }
                    } catch {}
                }
                result = "[" + string.Join(",", items.ToArray()) + "]";
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return result;
    }

    // Find top-level window by partial name
    private static AutomationElement FindTopWindow(string namePattern) {
        AutomationElement root = AutomationElement.RootElement;
        if (root == null) return null;
        AutomationElementCollection windows = root.FindAll(TreeScope.Children, Condition.TrueCondition);
        string lowerPattern = namePattern.ToLower();

        foreach (AutomationElement w in windows) {
            try {
                string wName = w.Current.Name;
                if (!string.IsNullOrEmpty(wName) && wName.ToLower().Contains(lowerPattern)) {
                    return w;
                }
            } catch {}
        }
        return null;
    }

    // 2. Get-WindowElements
    public static string GetWindowElementsJson(string windowName) {
        string result = "[]";
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                AutomationElement win = FindTopWindow(windowName);
                if (win == null) return;

                Condition cond = new PropertyCondition(AutomationElement.IsControlElementProperty, true);
                AutomationElementCollection elements = win.FindAll(TreeScope.Descendants, cond);
                List<string> items = new List<string>();
                int count = 0;

                foreach (AutomationElement el in elements) {
                    try {
                        string name = el.Current.Name;
                        string autoId = el.Current.AutomationId;
                        string cType = el.Current.ControlType.ProgrammaticName.Replace("ControlType.", "");
                        bool isOff = el.Current.IsOffscreen;
                        var rect = el.Current.BoundingRectangle;

                        if ((!string.IsNullOrWhiteSpace(name) || !string.IsNullOrWhiteSpace(autoId)) && !isOff && rect.Width > 0 && rect.Height > 0) {
                            string item = string.Format(
                                "{{\"name\":\"{0}\",\"type\":\"{1}\",\"automationId\":\"{2}\",\"bbox\":{{\"x\":{3},\"y\":{4},\"width\":{5},\"height\":{6}}}}}",
                                EscapeJson(name), EscapeJson(cType), EscapeJson(autoId), (int)rect.X, (int)rect.Y, (int)rect.Width, (int)rect.Height
                            );
                            items.Add(item);
                            count++;
                            if (count >= 100) break;
                        }
                    } catch {}
                }
                result = "[" + string.Join(",", items.ToArray()) + "]";
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return result;
    }

    // 3. Click-At
    public static bool ClickAt(int x, int y) {
        bool ok = false;
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                SetCursorPos(x, y);
                Thread.Sleep(30);

                INPUT[] inputs = new INPUT[2];
                inputs[0].type = INPUT_MOUSE;
                inputs[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
                inputs[1].type = INPUT_MOUSE;
                inputs[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;

                uint sent = SendInput(2, inputs, Marshal.SizeOf(typeof(INPUT)));
                ok = (sent == 2);
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return ok;
    }

    // 4. Scroll-At
    public static bool ScrollAt(int x, int y, int delta) {
        bool ok = false;
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                SetCursorPos(x, y);
                Thread.Sleep(30);

                INPUT[] inputs = new INPUT[1];
                inputs[0].type = INPUT_MOUSE;
                inputs[0].mi.dwFlags = MOUSEEVENTF_WHEEL;
                inputs[0].mi.mouseData = (uint)delta;

                uint sent = SendInput(1, inputs, Marshal.SizeOf(typeof(INPUT)));
                ok = (sent == 1);
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return ok;
    }

    // 5. Click-Element
    public static string ClickElement(string elementName) {
        string status = "I can't see that element";
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                AutomationElement root = AutomationElement.RootElement;
                if (root == null) return;

                string lowerTarget = elementName.ToLower();
                AutomationElement target = null;

                AutomationElement focused = AutomationElement.FocusedElement;
                AutomationElement activeWin = null;
                if (focused != null) {
                    try {
                        activeWin = TreeWalker.ControlViewWalker.GetParent(focused);
                    } catch {}
                }

                Condition cond = new PropertyCondition(AutomationElement.IsControlElementProperty, true);

                if (activeWin != null) {
                    try {
                        AutomationElementCollection inWin = activeWin.FindAll(TreeScope.Descendants, cond);
                        foreach (AutomationElement el in inWin) {
                            string eName = el.Current.Name;
                            string aId = el.Current.AutomationId;
                            if ((!string.IsNullOrEmpty(eName) && eName.ToLower().Contains(lowerTarget)) ||
                                (!string.IsNullOrEmpty(aId) && aId.ToLower().Contains(lowerTarget))) {
                                target = el;
                                break;
                            }
                        }
                    } catch {}
                }

                if (target == null) {
                    AutomationElementCollection allWins = root.FindAll(TreeScope.Children, Condition.TrueCondition);
                    foreach (AutomationElement w in allWins) {
                        try {
                            if (w.Current.IsOffscreen) continue;
                            AutomationElementCollection inWin = w.FindAll(TreeScope.Descendants, cond);
                            foreach (AutomationElement el in inWin) {
                                string eName = el.Current.Name;
                                string aId = el.Current.AutomationId;
                                if ((!string.IsNullOrEmpty(eName) && eName.ToLower().Contains(lowerTarget)) ||
                                    (!string.IsNullOrEmpty(aId) && aId.ToLower().Contains(lowerTarget))) {
                                    target = el;
                                    break;
                                }
                            }
                            if (target != null) break;
                        } catch {}
                    }
                }

                if (target != null) {
                    var rect = target.Current.BoundingRectangle;
                    if (rect.Width > 0 && rect.Height > 0) {
                        int cx = (int)(rect.X + rect.Width / 2);
                        int cy = (int)(rect.Y + rect.Height / 2);

                        object invokePattern;
                        if (target.TryGetCurrentPattern(InvokePattern.Pattern, out invokePattern)) {
                            ((InvokePattern)invokePattern).Invoke();
                            status = string.Format("Invoked '{0}' at ({1}, {2})", target.Current.Name, cx, cy);
                        } else {
                            SetCursorPos(cx, cy);
                            Thread.Sleep(30);
                            INPUT[] inputs = new INPUT[2];
                            inputs[0].type = INPUT_MOUSE;
                            inputs[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
                            inputs[1].type = INPUT_MOUSE;
                            inputs[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;
                            SendInput(2, inputs, Marshal.SizeOf(typeof(INPUT)));
                            status = string.Format("Clicked '{0}' at ({1}, {2})", target.Current.Name, cx, cy);
                        }
                    }
                }
            } catch (Exception ex) {
                status = "Error: " + ex.Message;
            }
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return status;
    }

    // 6. TypeString (SendInput with Unicode characters)
    public static bool TypeString(string text) {
        bool ok = false;
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                INPUT[] inputs = new INPUT[text.Length * 2];
                for (int i = 0; i < text.Length; i++) {
                    char c = text[i];
                    inputs[i * 2].type = INPUT_KEYBOARD;
                    inputs[i * 2].ki.wVk = 0;
                    inputs[i * 2].ki.wScan = (ushort)c;
                    inputs[i * 2].ki.dwFlags = KEYEVENTF_UNICODE;

                    inputs[i * 2 + 1].type = INPUT_KEYBOARD;
                    inputs[i * 2 + 1].ki.wVk = 0;
                    inputs[i * 2 + 1].ki.wScan = (ushort)c;
                    inputs[i * 2 + 1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
                }
                uint sent = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf(typeof(INPUT)));
                ok = (sent == inputs.Length);
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return ok;
    }

    // 7. SendVirtualKey
    private static INPUT MakeKey(ushort vk, bool keyUp) {
        INPUT inp = new INPUT();
        inp.type = INPUT_KEYBOARD;
        inp.ki.wVk = vk;
        inp.ki.wScan = 0;
        inp.ki.dwFlags = keyUp ? KEYEVENTF_KEYUP : 0;
        return inp;
    }

    public static bool SendVirtualKey(ushort vk, bool ctrl, bool alt, bool shift) {
        bool ok = false;
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                List<INPUT> list = new List<INPUT>();
                if (ctrl) list.Add(MakeKey(0x11, false));  // VK_CONTROL
                if (alt) list.Add(MakeKey(0x12, false));   // VK_MENU
                if (shift) list.Add(MakeKey(0x10, false)); // VK_SHIFT

                list.Add(MakeKey(vk, false));
                list.Add(MakeKey(vk, true));

                if (shift) list.Add(MakeKey(0x10, true));
                if (alt) list.Add(MakeKey(0x12, true));
                if (ctrl) list.Add(MakeKey(0x11, true));

                uint sent = SendInput((uint)list.Count, list.ToArray(), Marshal.SizeOf(typeof(INPUT)));
                ok = (sent == list.Count);
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return ok;
    }

    // 8. Focus-Window
    public static bool FocusWindow(string windowName) {
        bool ok = false;
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                AutomationElement win = FindTopWindow(windowName);
                if (win != null) {
                    IntPtr handle = new IntPtr(win.Current.NativeWindowHandle);
                    if (handle != IntPtr.Zero) {
                        ShowWindow(handle, SW_RESTORE);
                        SetForegroundWindow(handle);
                    }
                    win.SetFocus();
                    ok = true;
                }
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return ok;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    public struct STARTUPINFO {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX;
        public int dwY;
        public int dwXSize;
        public int dwYSize;
        public int dwXCountChars;
        public int dwYCountChars;
        public int dwFillAttribute;
        public int dwFlags;
        public short wShowWindow;
        public short cbReserved2;
        public IntPtr lpReserved2;
        public IntPtr hStdInput;
        public IntPtr hStdOutput;
        public IntPtr hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION {
        public IntPtr hProcess;
        public IntPtr hThread;
        public int dwProcessId;
        public int dwThreadId;
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern bool CreateProcess(
        string lpApplicationName,
        string lpCommandLine,
        IntPtr lpProcessAttributes,
        IntPtr lpThreadAttributes,
        bool bInheritHandles,
        uint dwCreationFlags,
        IntPtr lpEnvironment,
        string lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo,
        out PROCESS_INFORMATION lpProcessInformation
    );

    public static bool LaunchApp(string appName) {
        try {
            string cmd = appName;
            if (!cmd.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) && !cmd.Contains(" ") && !cmd.Contains("\\") && !cmd.Contains("/")) {
                cmd = cmd + ".exe";
            }
            STARTUPINFO si = new STARTUPINFO();
            si.cb = Marshal.SizeOf(typeof(STARTUPINFO));
            si.lpDesktop = "WinSta0\\Default";
            PROCESS_INFORMATION pi = new PROCESS_INFORMATION();
            bool ok = CreateProcess(null, cmd, IntPtr.Zero, IntPtr.Zero, false, 0, IntPtr.Zero, null, ref si, out pi);
            if (ok) return true;
        } catch {}
        try {
            Process.Start(appName);
            return true;
        } catch {
            return false;
        }
    }

    // 9. Close-Window
    public static bool CloseWindow(string windowName) {
        bool ok = false;
        Thread t = new Thread(() => {
            try {
                AttachToDefaultDesktop();
                AutomationElement win = FindTopWindow(windowName);
                if (win != null) {
                    object winPat;
                    if (win.TryGetCurrentPattern(WindowPattern.Pattern, out winPat)) {
                        ((WindowPattern)winPat).Close();
                        ok = true;
                    } else {
                        IntPtr handle = new IntPtr(win.Current.NativeWindowHandle);
                        if (handle != IntPtr.Zero) {
                            PostMessage(handle, WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
                            ok = true;
                        }
                    }
                }
            } catch {}
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return ok;
    }
}
'@

if (-not ([System.Management.Automation.PSTypeName]'UIAutomationHelper').Type) {
    Add-Type -ReferencedAssemblies "UIAutomationClient", "UIAutomationTypes", "WindowsBase" -TypeDefinition $code
}

Add-Type -AssemblyName System.Windows.Forms

# 1. Get-OpenWindows
function Get-OpenWindows {
    [CmdletBinding()]
    param()
    [UIAutomationHelper]::GetWindowsJson()
}

# 2. Get-WindowElements -Name <string>
function Get-WindowElements {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Name
    )
    [UIAutomationHelper]::GetWindowElementsJson($Name)
}

# 3. Start-App -Name <string>
function Start-App {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Name
    )
    $cleanName = $Name.Trim().Trim('"').Trim("'")
    $cleanQuery = ($cleanName -replace '[^a-zA-Z0-9]', '').ToLower()

    # 1. Check if command exists in PATH directly (e.g. notepad, code, wt)
    $pathCmd = Get-Command $cleanName -ErrorAction SilentlyContinue
    if ($pathCmd) {
        $ok = [UIAutomationHelper]::LaunchApp($pathCmd.Source)
        if (-not $ok) { Start-Process $pathCmd.Source }
        "Launched: $cleanName"
        return
    }

    # 2. Dynamic Windows Application Discovery (Get-StartApps) - zero hardcoding required!
    # Inspects all installed Win32, UWP, and Store apps registered with Windows
    $apps = Get-StartApps -ErrorAction SilentlyContinue
    if ($apps) {
        $matchedApp = $apps | Where-Object {
            $n = $_.Name.ToLower()
            $cn = ($_.Name -replace '[^a-zA-Z0-9]', '').ToLower()
            $id = $_.AppID.ToLower()

            # Exact or substring match (e.g. "google chrome" -> "chrome")
            if ($cn.Contains($cleanQuery) -or $id.Contains($cleanQuery) -or $n.Contains($cleanName.ToLower()) -or $cleanName.ToLower().Contains($n)) { return $true }

            # Acronym match (e.g. "vsc" or "vscode" for "Visual Studio Code")
            $words = $_.Name -split '\s+'
            $initials = (($words | ForEach-Object { if ($_.Length -gt 0) { $_.Substring(0,1) } }) -join '').ToLower()
            if ($initials -eq $cleanQuery) { return $true }

            # Compound acronym: initials of prefix words + last word (e.g. 'vs' + 'code' for 'Visual Studio Code')
            if ($words.Count -ge 2) {
                $prefixInitials = (($words[0..($words.Count-2)] | ForEach-Object { $_.Substring(0,1) }) -join '').ToLower()
                $lastWord = $words[-1].ToLower()
                if (($prefixInitials + $lastWord) -eq $cleanQuery) { return $true }
            }
            return $false
        } | Select-Object -First 1

        if ($matchedApp) {
            try {
                Start-Process "shell:AppsFolder\$($matchedApp.AppID)"
                "Launched: $($matchedApp.Name)"
                return
            } catch {}
        }
    }

    # 3. Check Windows Start Menu shortcuts (.lnk files)
    $searchPattern = ($cleanName -replace "\s+", "*")
    $shortcut = Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu", "$env:ProgramData\Microsoft\Windows\Start Menu" -Filter "*$searchPattern*.lnk" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($shortcut) {
        $ok = [UIAutomationHelper]::LaunchApp($shortcut.FullName)
        if (-not $ok) { Start-Process $shortcut.FullName }
        "Launched: $($shortcut.BaseName)"
        return
    }

    # 4. Fallback: Well-known developer aliases (for tools without Start menu shortcuts)
    $aliases = @{
        "vscode" = "code"
        "vs code" = "code"
        "visual studio code" = "code"
        "terminal" = "wt"
        "word" = "winword"
        "excel" = "excel"
        "powerpoint" = "powerpnt"
    }
    $resolved = if ($aliases.ContainsKey($cleanName.ToLower())) { $aliases[$cleanName.ToLower()] } else { $cleanName }
    $resolvedCmd = Get-Command $resolved -ErrorAction SilentlyContinue
    if ($resolvedCmd) {
        $ok = [UIAutomationHelper]::LaunchApp($resolvedCmd.Source)
        if (-not $ok) { Start-Process $resolvedCmd.Source }
        "Launched: $cleanName"
        return
    }

    # 5. Fallback to direct executable / protocol launch
    $ok = [UIAutomationHelper]::LaunchApp($resolved)
    if (-not $ok) {
        try {
            Start-Process $resolved
            $ok = $true
        } catch {}
    }
    if ($ok) { "Launched: $cleanName" } else { "Failed to launch: $cleanName" }
}

# 4. Click-At -X <int> -Y <int>
function Click-At {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [int]$X,
        [Parameter(Mandatory = $true, Position = 1)]
        [int]$Y
    )
    $ok = [UIAutomationHelper]::ClickAt($X, $Y)
    if ($ok) { "Clicked at ($X, $Y)" } else { "Failed to click at ($X, $Y)" }
}

# 5. Click-Element -Name <string>
function Click-Element {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Name
    )
    [UIAutomationHelper]::ClickElement($Name)
}

# 6. Type-Text -Text <string>
function Type-Text {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Text
    )
    # Prefer SendInput with Unicode support for desktop resilience
    $ok = [UIAutomationHelper]::TypeString($Text)
    if (-not $ok) {
        # Fallback to SendKeys
        try {
            $escaped = ""
            foreach ($c in $Text.ToCharArray()) {
                if ("+^%~(){}[]".Contains($c)) {
                    $escaped += "{$c}"
                } else {
                    $escaped += $c
                }
            }
            [System.Windows.Forms.SendKeys]::SendWait($escaped)
            $ok = $true
        } catch {}
    }
    if ($ok) { "Typed: $Text" } else { "Failed to type: $Text" }
}

# 7. Press-Hotkey -Keys <string>
function Press-Hotkey {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Keys
    )
    $lower = $Keys.ToLower()
    $handled = $false
    if ($lower -in @("{enter}", "enter")) {
        $handled = [UIAutomationHelper]::SendVirtualKey(0x0D, $false, $false, $false)
    } elseif ($lower -in @("{esc}", "{escape}", "esc", "escape")) {
        $handled = [UIAutomationHelper]::SendVirtualKey(0x1B, $false, $false, $false)
    } elseif ($lower -in @("{tab}", "tab")) {
        $handled = [UIAutomationHelper]::SendVirtualKey(0x09, $false, $false, $false)
    } elseif ($lower -in @("^s", "ctrl+s")) {
        $handled = [UIAutomationHelper]::SendVirtualKey(0x53, $true, $false, $false)
    } elseif ($lower -in @("%{f4}", "alt+f4")) {
        $handled = [UIAutomationHelper]::SendVirtualKey(0x73, $false, $true, $false)
    }

    if (-not $handled) {
        try {
            [System.Windows.Forms.SendKeys]::SendWait($Keys)
            $handled = $true
        } catch {}
    }
    if ($handled) { "Pressed: $Keys" } else { "Failed to press hotkey: $Keys" }
}

# 8. Scroll-At -X <int> -Y <int> -Delta <int>
function Scroll-At {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [int]$X,
        [Parameter(Mandatory = $true, Position = 1)]
        [int]$Y,
        [Parameter(Mandatory = $true, Position = 2)]
        [int]$Delta
    )
    $ok = [UIAutomationHelper]::ScrollAt($X, $Y, $Delta)
    if ($ok) { "Scrolled at ($X, $Y) with delta $Delta" } else { "Failed to scroll at ($X, $Y)" }
}

# 9. Close-Window -Name <string>
function Close-Window {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Name
    )
    $ok = [UIAutomationHelper]::CloseWindow($Name)
    if ($ok) { "Closed window '$Name'" } else { "Window '$Name' not found or could not be closed" }
}

# 10. Focus-Window -Name <string>
function Focus-Window {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Name
    )
    $ok = [UIAutomationHelper]::FocusWindow($Name)
    if ($ok) { "Focused window '$Name'" } else { "Window '$Name' not found" }
}
