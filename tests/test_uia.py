"""Unit tests for Windows UI Automation primitives and Milestone 1 features."""

import json
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import safety
import generator
from jevterm import summarize_open_windows, execute_powershell


class TestUIAutomationMilestone1(unittest.TestCase):
    def test_safety_allows_uia_primitives(self):
        primitives = [
            "Get-OpenWindows",
            "Get-WindowElements -Name 'Notepad'",
            "Start-App -Name notepad",
            "Click-At -X 500 -Y 300",
            "Click-Element -Name 'OK'",
            "Type-Text -Text 'hello world'",
            "Press-Hotkey -Keys '{ENTER}'",
            "Scroll-At -X 500 -Y 300 -Delta -120",
            "Focus-Window -Name 'Notepad'",
        ]
        for cmd in primitives:
            is_safe, reason = safety.check_safety(cmd)
            self.assertTrue(is_safe, f"Expected {cmd} to pass safety check, got {reason}")

    def test_summarize_open_windows(self):
        sample_json = json.dumps([
            {"name": "Interview Problems - LeetCode - Google Chrome", "process": "chrome", "pid": 101, "bbox": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
            {"name": "NLPTerminal - Antigravity IDE", "process": "Antigravity IDE", "pid": 102, "bbox": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
            {"name": "Program Manager", "process": "explorer", "pid": 103, "bbox": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
        ])

        summary = summarize_open_windows(sample_json)
        self.assertIn("open window", summary.lower())
        self.assertIn("Interview Problems - LeetCode - Google Chrome", summary)
        self.assertIn("NLPTerminal - Antigravity IDE", summary)
        # Program Manager should be filtered out
        self.assertNotIn("Program Manager", summary)

    def test_summarize_empty_windows(self):
        summary = summarize_open_windows("[]")
        self.assertIn("no open application windows", summary.lower())

    def test_mock_generator_routing(self):
        intents = [
            "what windows are open?",
            "what's on my screen?",
            "what's open?",
            "whats on my screen",
        ]
        for intent in intents:
            result = generator.generate_command(intent, use_mock=True)
            self.assertEqual(result.get("command"), "Get-OpenWindows")
            self.assertEqual(result.get("risk"), "low")

    def test_get_open_windows_execution(self):
        exit_code, stdout_str = execute_powershell("Get-OpenWindows")
        self.assertEqual(exit_code, 0)
        # Should contain a JSON array
        self.assertTrue(stdout_str.strip().startswith("[") and stdout_str.strip().endswith("]"))
        windows = json.loads(stdout_str.strip())
        self.assertIsInstance(windows, list)
        self.assertGreater(len(windows), 0)
        # Verify schema of each window object
        for w in windows:
            self.assertIn("name", w)
            self.assertIn("process", w)
            self.assertIn("pid", w)
            self.assertIn("bbox", w)
            self.assertIn("x", w["bbox"])
            self.assertIn("y", w["bbox"])
            self.assertIn("width", w["bbox"])
            self.assertIn("height", w["bbox"])


class TestUIAutomationMilestone2(unittest.TestCase):
    def test_open_notepad_and_type_generation(self):
        res = generator.generate_command("open Notepad and type hello world", use_mock=False)
        cmd = res.get("command", "")
        self.assertIn("Start-App -Name notepad", cmd)
        self.assertIn("Type-Text -Text 'hello world'", cmd)

    def test_open_notepad_and_type_mock(self):
        res = generator.generate_command("open Notepad and type hello world", use_mock=True)
        cmd = res.get("command", "")
        self.assertIn("Start-App -Name notepad", cmd)
        self.assertIn("Type-Text -Text 'hello world'", cmd)

    def test_click_element_not_found(self):
        exit_code, stdout_str = execute_powershell("Click-Element -Name 'NonExistentButtonXYZ'")
        self.assertEqual(exit_code, 0)
        self.assertIn("I can't see that element", stdout_str)


if __name__ == "__main__":
    unittest.main()
