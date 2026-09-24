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
    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    public const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
    public const uint MOUSEEVENTF_RIGHTUP = 0x0010;
    public const uint MOUSEEVENTF_WHEEL = 0x0800;
    public const uint WM_CLOSE = 0x0010;
    public const int SW_RESTORE = 9;

    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT {
        public uint type;
        public MOUSEINPUT mi;
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

                // Search descendants for interactive or named controls
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

                        // Include if has a name or automation id, and visible dimensions
                        if ((!string.IsNullOrWhiteSpace(name) || !string.IsNullOrWhiteSpace(autoId)) && !isOff && rect.Width > 0 && rect.Height > 0) {
                            string item = string.Format(
                                "{{\"name\":\"{0}\",\"type\":\"{1}\",\"automationId\":\"{2}\",\"bbox\":{{\"x\":{3},\"y\":{4},\"width\":{5},\"height\":{6}}}}}",
                                EscapeJson(name), EscapeJson(cType), EscapeJson(autoId), (int)rect.X, (int)rect.Y, (int)rect.Width, (int)rect.Height
                            );
                            items.Add(item);
                            count++;
                            if (count >= 100) break; // Performance guardrail
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

                SendInput(2, inputs, Marshal.SizeOf(typeof(INPUT)));
                ok = true;
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

                SendInput(1, inputs, Marshal.SizeOf(typeof(INPUT)));
                ok = true;
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

                // First search in focused top window, then all windows
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

                        // Try invoke pattern if available, or click coordinates
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

    // 6. Focus-Window
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

    // 7. Close-Window
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
    Start-Process $Name
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
    # Escape special characters for SendKeys: + ^ % ~ ( ) { } [ ]
    $escaped = ""
    foreach ($c in $Text.ToCharArray()) {
        if ("+^%~(){}[]".Contains($c)) {
            $escaped += "{$c}"
        } else {
            $escaped += $c
        }
    }
    [System.Windows.Forms.SendKeys]::SendWait($escaped)
    "Typed: $Text"
}

# 7. Press-Hotkey -Keys <string>
function Press-Hotkey {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Keys
    )
    [System.Windows.Forms.SendKeys]::SendWait($Keys)
    "Pressed: $Keys"
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
