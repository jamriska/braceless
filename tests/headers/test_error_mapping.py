#!/usr/bin/env python3
"""
Tests for error message line number mapping.

These tests verify that compiler error messages are correctly patched
to show the original source file and line number, not the temporary
transpiled file locations.
"""

import unittest
import sys
import os
import re
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@dataclass
class SourceLocation:
    """Represents a location in a source file"""
    file: str
    line: int


# =============================================================================
# Error message patterns (from blcc.py, extended for chained mapping)
# =============================================================================

# MSVC-style: file(line): or file(line,col):
MSVC_ERROR_PATTERN = re.compile(
    r'^(.*?)\((\d+)(,\d+)?\)\s*:\s*(error|warning|note|fatal error)',
    re.IGNORECASE
)

# GNU-style: file:line:col: or file:line:
GNU_ERROR_PATTERN = re.compile(
    r'^(.+?):(\d+):(\d+)?:?\s*(error|warning|note|fatal error)',
    re.IGNORECASE
)


def patch_error_line_gnu(
    error_line: str,
    temp_file: str,
    line_map: Dict[int, SourceLocation]
) -> str:
    """Patch a GNU-style error message with correct source location.
    
    Args:
        error_line: The error message line from compiler
        temp_file: Path to the temporary transpiled file
        line_map: Mapping from transpiled line -> original SourceLocation
        
    Returns:
        Patched error line with original file/line, or original if no match
    """
    match = GNU_ERROR_PATTERN.match(error_line)
    if not match:
        return error_line
    
    filepath = match.group(1)
    line_num = int(match.group(2))
    col = match.group(3)
    
    # Check if this error is from our temp file
    # Normalize paths for comparison
    if not _paths_match(filepath, temp_file):
        return error_line
    
    # Look up the original location
    if line_num not in line_map:
        return error_line
    
    loc = line_map[line_num]
    
    # Build the replacement
    if col:
        old_prefix = f"{filepath}:{line_num}:{col}:"
        new_prefix = f"{loc.file}:{loc.line}:{col}:"
    else:
        old_prefix = f"{filepath}:{line_num}:"
        new_prefix = f"{loc.file}:{loc.line}:"
    
    return error_line.replace(old_prefix, new_prefix, 1)


def patch_error_line_msvc(
    error_line: str,
    temp_file: str,
    line_map: Dict[int, SourceLocation]
) -> str:
    """Patch an MSVC-style error message with correct source location.
    
    Args:
        error_line: The error message line from compiler
        temp_file: Path to the temporary transpiled file
        line_map: Mapping from transpiled line -> original SourceLocation
        
    Returns:
        Patched error line with original file/line, or original if no match
    """
    match = MSVC_ERROR_PATTERN.match(error_line)
    if not match:
        return error_line
    
    filepath = match.group(1)
    line_num = int(match.group(2))
    col_part = match.group(3) or ''
    
    # Check if this error is from our temp file
    if not _paths_match(filepath, temp_file):
        return error_line
    
    # Look up the original location
    if line_num not in line_map:
        return error_line
    
    loc = line_map[line_num]
    
    # Build the replacement
    old_loc = f"({line_num}{col_part})"
    new_loc = f"({loc.line}{col_part})"
    
    result = error_line.replace(filepath, loc.file, 1)
    result = result.replace(old_loc, new_loc, 1)
    
    return result


def _paths_match(path1: str, path2: str) -> bool:
    """Check if two paths refer to the same file (case-insensitive on Windows)"""
    import os
    norm1 = os.path.normcase(os.path.normpath(path1))
    norm2 = os.path.normcase(os.path.normpath(path2))
    if norm1 == norm2:
        return True
    # Also check basename match for temp files
    return os.path.basename(path1).lower() == os.path.basename(path2).lower()


def patch_compiler_output(
    output: str,
    temp_file: str,
    line_map: Dict[int, SourceLocation],
    is_msvc: bool = False
) -> str:
    """Patch all error messages in compiler output.
    
    Args:
        output: Full compiler output (stdout or stderr)
        temp_file: Path to the temporary transpiled file
        line_map: Mapping from transpiled line -> original SourceLocation
        is_msvc: True for MSVC-style errors, False for GNU-style
        
    Returns:
        Patched output with corrected file/line references
    """
    patch_func = patch_error_line_msvc if is_msvc else patch_error_line_gnu
    
    lines = output.split('\n')
    patched = [patch_func(line, temp_file, line_map) for line in lines]
    return '\n'.join(patched)


# =============================================================================
# Test Cases
# =============================================================================

class TestGnuErrorPatching(unittest.TestCase):
    """Tests for GNU-style error message patching"""

    def setUp(self):
        self.temp_file = "/tmp/blcc_xyz123/main.cpp"
        self.line_map = {
            5: SourceLocation("math_utils.blh", 3),
            10: SourceLocation("math_utils.blh", 8),
            15: SourceLocation("main.blcpp", 5),
            20: SourceLocation("main.blcpp", 10),
        }

    def test_patch_simple_error(self):
        """Patch a simple error message"""
        error = "/tmp/blcc_xyz123/main.cpp:5:10: error: expected ';'"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertEqual(result, "math_utils.blh:3:10: error: expected ';'")

    def test_patch_warning(self):
        """Patch a warning message"""
        error = "/tmp/blcc_xyz123/main.cpp:10:1: warning: unused variable 'x'"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertEqual(result, "math_utils.blh:8:1: warning: unused variable 'x'")

    def test_patch_note(self):
        """Patch a note message"""
        error = "/tmp/blcc_xyz123/main.cpp:15:5: note: in expansion of macro"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertEqual(result, "main.blcpp:5:5: note: in expansion of macro")

    def test_patch_fatal_error(self):
        """Patch a fatal error message"""
        error = "/tmp/blcc_xyz123/main.cpp:20:1: fatal error: too many errors"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertEqual(result, "main.blcpp:10:1: fatal error: too many errors")

    def test_no_patch_different_file(self):
        """Don't patch errors from different files"""
        error = "/usr/include/vector:123:5: error: something"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertEqual(result, error)  # Unchanged

    def test_no_patch_unknown_line(self):
        """Don't patch if line not in map"""
        error = "/tmp/blcc_xyz123/main.cpp:999:1: error: unknown line"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertEqual(result, error)  # Unchanged

    def test_no_patch_non_error(self):
        """Don't patch non-error lines"""
        lines = [
            "In file included from main.cpp:1:",
            "         int x = 5;",
            "             ^",
        ]
        for line in lines:
            result = patch_error_line_gnu(line, self.temp_file, self.line_map)
            self.assertEqual(result, line)  # Unchanged

    def test_patch_without_column(self):
        """Patch error without column number"""
        error = "/tmp/blcc_xyz123/main.cpp:5: error: something"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertEqual(result, "math_utils.blh:3: error: something")

    def test_preserve_rest_of_line(self):
        """Rest of error message should be preserved"""
        error = "/tmp/blcc_xyz123/main.cpp:5:10: error: use of undeclared identifier 'foo'; did you mean 'bar'?"
        result = patch_error_line_gnu(error, self.temp_file, self.line_map)
        self.assertIn("use of undeclared identifier 'foo'", result)
        self.assertIn("did you mean 'bar'?", result)


class TestMsvcErrorPatching(unittest.TestCase):
    """Tests for MSVC-style error message patching"""

    def setUp(self):
        self.temp_file = r"C:\temp\blcc_xyz123\main.cpp"
        self.line_map = {
            5: SourceLocation("math_utils.blh", 3),
            10: SourceLocation("math_utils.blh", 8),
            15: SourceLocation("main.blcpp", 5),
            20: SourceLocation("main.blcpp", 10),
        }

    def test_patch_simple_error(self):
        """Patch a simple MSVC error"""
        error = r"C:\temp\blcc_xyz123\main.cpp(5): error C2143: syntax error: missing ';'"
        result = patch_error_line_msvc(error, self.temp_file, self.line_map)
        self.assertEqual(result, "math_utils.blh(3): error C2143: syntax error: missing ';'")

    def test_patch_with_column(self):
        """Patch MSVC error with column"""
        error = r"C:\temp\blcc_xyz123\main.cpp(10,15): error C2065: 'foo': undeclared identifier"
        result = patch_error_line_msvc(error, self.temp_file, self.line_map)
        self.assertEqual(result, "math_utils.blh(8,15): error C2065: 'foo': undeclared identifier")

    def test_patch_warning(self):
        """Patch MSVC warning"""
        error = r"C:\temp\blcc_xyz123\main.cpp(15): warning C4101: 'x': unreferenced local variable"
        result = patch_error_line_msvc(error, self.temp_file, self.line_map)
        self.assertEqual(result, "main.blcpp(5): warning C4101: 'x': unreferenced local variable")

    def test_patch_note(self):
        """Patch MSVC note"""
        error = r"C:\temp\blcc_xyz123\main.cpp(20): note: see declaration of 'foo'"
        result = patch_error_line_msvc(error, self.temp_file, self.line_map)
        self.assertEqual(result, "main.blcpp(10): note: see declaration of 'foo'")

    def test_no_patch_different_file(self):
        """Don't patch errors from different files"""
        error = r"C:\Program Files\VC\include\vector(123): error: something"
        result = patch_error_line_msvc(error, self.temp_file, self.line_map)
        self.assertEqual(result, error)


class TestFullOutputPatching(unittest.TestCase):
    """Tests for patching complete compiler output"""

    def setUp(self):
        self.temp_file = "/tmp/blcc_test/main.cpp"
        self.line_map = {
            3: SourceLocation("header.blh", 1),
            4: SourceLocation("header.blh", 2),
            5: SourceLocation("header.blh", 3),
            10: SourceLocation("main.blcpp", 5),
            11: SourceLocation("main.blcpp", 6),
            12: SourceLocation("main.blcpp", 7),
        }

    def test_patch_multiple_errors(self):
        """Patch multiple errors in output"""
        output = """\
/tmp/blcc_test/main.cpp:3:5: error: expected ';'
/tmp/blcc_test/main.cpp:10:10: error: use of undeclared identifier 'x'
/tmp/blcc_test/main.cpp:12:1: warning: control reaches end of non-void function
"""
        result = patch_compiler_output(output, self.temp_file, self.line_map)
        
        self.assertIn("header.blh:1:5: error:", result)
        self.assertIn("main.blcpp:5:10: error:", result)
        self.assertIn("main.blcpp:7:1: warning:", result)

    def test_patch_error_with_context(self):
        """Patch error that includes source context"""
        output = """\
/tmp/blcc_test/main.cpp:3:5: error: expected ';'
    int x = 5
        ^
        ;
"""
        result = patch_compiler_output(output, self.temp_file, self.line_map)
        
        # Error line should be patched
        self.assertIn("header.blh:1:5: error:", result)
        # Context lines should be preserved
        self.assertIn("int x = 5", result)
        self.assertIn("^", result)

    def test_patch_error_chain(self):
        """Patch error with associated notes"""
        output = """\
/tmp/blcc_test/main.cpp:10:5: error: no matching function for call to 'foo'
/tmp/blcc_test/main.cpp:3:1: note: candidate function not viable
"""
        result = patch_compiler_output(output, self.temp_file, self.line_map)
        
        self.assertIn("main.blcpp:5:5: error:", result)
        self.assertIn("header.blh:1:1: note:", result)

    def test_preserve_non_error_lines(self):
        """Non-error lines should be preserved unchanged"""
        output = """\
In file included from /tmp/blcc_test/main.cpp:1:
/tmp/blcc_test/main.cpp:3:5: error: expected ';'
1 error generated.
"""
        result = patch_compiler_output(output, self.temp_file, self.line_map)
        
        self.assertIn("In file included from", result)
        self.assertIn("1 error generated.", result)

    def test_mixed_files_in_output(self):
        """Handle output with errors from multiple files"""
        output = """\
/tmp/blcc_test/main.cpp:3:5: error: in our file
/usr/include/vector:100:10: error: in system header
/tmp/blcc_test/main.cpp:10:1: warning: another in our file
"""
        result = patch_compiler_output(output, self.temp_file, self.line_map)
        
        # Our file errors should be patched
        self.assertIn("header.blh:1:5: error:", result)
        self.assertIn("main.blcpp:5:1: warning:", result)
        # System header error should be unchanged
        self.assertIn("/usr/include/vector:100:10: error:", result)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and special scenarios"""

    def test_empty_output(self):
        """Handle empty compiler output"""
        result = patch_compiler_output("", "/tmp/test.cpp", {})
        self.assertEqual(result, "")

    def test_no_errors(self):
        """Handle output with no errors"""
        output = "Compilation successful.\n"
        result = patch_compiler_output(output, "/tmp/test.cpp", {})
        self.assertEqual(result, output)

    def test_path_with_spaces(self):
        """Handle paths with spaces"""
        temp_file = "/tmp/my project/main.cpp"
        line_map = {5: SourceLocation("my header.blh", 3)}
        
        error = "/tmp/my project/main.cpp:5:1: error: test"
        result = patch_error_line_gnu(error, temp_file, line_map)
        self.assertIn("my header.blh:3:1:", result)

    def test_very_long_line_number(self):
        """Handle large line numbers"""
        line_map = {99999: SourceLocation("big_file.blh", 88888)}
        error = "/tmp/test.cpp:99999:1: error: test"
        result = patch_error_line_gnu(error, "/tmp/test.cpp", line_map)
        self.assertIn("big_file.blh:88888:1:", result)

    def test_unicode_in_path(self):
        """Handle unicode characters in paths"""
        temp_file = "/tmp/tëst/main.cpp"
        line_map = {5: SourceLocation("hëader.blh", 3)}
        
        error = "/tmp/tëst/main.cpp:5:1: error: test"
        result = patch_error_line_gnu(error, temp_file, line_map)
        self.assertIn("hëader.blh:3:1:", result)


class TestRealWorldScenarios(unittest.TestCase):
    """Tests based on real compiler output patterns"""

    def test_clang_template_error(self):
        """Clang template instantiation error chain"""
        temp_file = "/tmp/blcc/main.cpp"
        line_map = {
            10: SourceLocation("container.blh", 5),
            15: SourceLocation("main.blcpp", 8),
        }
        
        output = """\
/tmp/blcc/main.cpp:10:15: error: no member named 'push_back' in 'std::array<int, 10>'
        arr.push_back(x);
            ^
/tmp/blcc/main.cpp:15:5: note: in instantiation of function template specialization
    process<std::array<int, 10>>(arr);
    ^
"""
        result = patch_compiler_output(output, temp_file, line_map)
        
        self.assertIn("container.blh:5:15: error:", result)
        self.assertIn("main.blcpp:8:5: note:", result)

    def test_gcc_include_chain(self):
        """GCC error with include chain"""
        temp_file = "/tmp/blcc/main.cpp"
        line_map = {
            5: SourceLocation("utils.blh", 10),
        }
        
        output = """\
In file included from /tmp/blcc/main.cpp:1:
/tmp/blcc/main.cpp:5:1: error: expected class-name before '{' token
 class Derived : public Base {
 ^~~~~
"""
        result = patch_compiler_output(output, temp_file, line_map)
        
        self.assertIn("utils.blh:10:1: error:", result)

    def test_msvc_linker_error(self):
        """MSVC linker errors (should not be patched - no line numbers)"""
        output = """\
main.obj : error LNK2019: unresolved external symbol "void __cdecl foo(void)"
"""
        result = patch_compiler_output(output, r"C:\temp\main.cpp", {}, is_msvc=True)
        self.assertEqual(result, output)  # Unchanged - linker error


if __name__ == '__main__':
    unittest.main(verbosity=2)
