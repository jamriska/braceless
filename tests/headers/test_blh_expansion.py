#!/usr/bin/env python3
"""
Tests for .blh header expansion.

These tests verify that:
1. .blh files are correctly expanded inline
2. Source locations are tracked for error mapping
3. #pragma once / include guards work correctly
4. Nested includes are handled properly
"""

import unittest
import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path to import blcc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from blcc import (
    expand_blh_includes,
    resolve_include,
    SourceLocationMapper,
    Compiler,
    MappingCompiler,
)


class TestResolveInclude(unittest.TestCase):
    """Tests for resolve_include function"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='blcc_test_')
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_resolve_in_same_dir(self):
        """Find header in same directory"""
        header = Path(self.temp_dir) / "test.blh"
        header.write_text("// test")
        
        result = resolve_include("test.blh", [self.temp_dir])
        self.assertIsNotNone(result)
        self.assertTrue(result.endswith("test.blh"))

    def test_resolve_in_include_dir(self):
        """Find header in include directory"""
        inc_dir = Path(self.temp_dir) / "include"
        inc_dir.mkdir()
        header = inc_dir / "test.blh"
        header.write_text("// test")
        
        result = resolve_include("test.blh", [str(inc_dir)])
        self.assertIsNotNone(result)

    def test_resolve_not_found(self):
        """Return None when header not found"""
        result = resolve_include("nonexistent.blh", [self.temp_dir])
        self.assertIsNone(result)

    def test_resolve_first_match_wins(self):
        """First matching directory wins"""
        dir1 = Path(self.temp_dir) / "dir1"
        dir2 = Path(self.temp_dir) / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        
        (dir1 / "test.blh").write_text("// dir1")
        (dir2 / "test.blh").write_text("// dir2")
        
        result = resolve_include("test.blh", [str(dir1), str(dir2)])
        self.assertIn("dir1", result)


class TestExpandBlhIncludes(unittest.TestCase):
    """Tests for expand_blh_includes function"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='blcc_test_')
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_no_includes(self):
        """File with no .blh includes passes through unchanged"""
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text("int main():\n    return 0\n")
        
        lines, line_map = expand_blh_includes(str(source))
        
        self.assertEqual(len(lines), 2)
        self.assertEqual(line_map[1][1], 1)  # Line 1 maps to source line 1
        self.assertEqual(line_map[2][1], 2)  # Line 2 maps to source line 2

    def test_simple_include(self):
        """Simple .blh include is expanded"""
        header = Path(self.temp_dir) / "header.blh"
        header.write_text("int foo():\n    return 1\n")
        
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('#include "header.blh"\nint main():\n    return foo()\n')
        
        lines, line_map = expand_blh_includes(str(source))
        
        # Should have: header line 1, header line 2, main line 2, main line 3
        self.assertEqual(len(lines), 4)
        
        # First two lines should map to header.blh
        self.assertIn("header.blh", line_map[1][0])
        self.assertIn("header.blh", line_map[2][0])
        
        # Last two lines should map to main.blcpp
        self.assertIn("main.blcpp", line_map[3][0])
        self.assertIn("main.blcpp", line_map[4][0])

    def test_nested_includes(self):
        """Nested .blh includes are expanded"""
        inner = Path(self.temp_dir) / "inner.blh"
        inner.write_text("int inner():\n    return 1\n")
        
        outer = Path(self.temp_dir) / "outer.blh"
        outer.write_text('#include "inner.blh"\nint outer():\n    return inner()\n')
        
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('#include "outer.blh"\nint main():\n    return outer()\n')
        
        lines, line_map = expand_blh_includes(str(source))
        
        # Should have content from all three files
        self.assertGreater(len(lines), 4)
        
        # Should have mappings to all three files
        files = set(loc[0] for loc in line_map.values())
        file_names = [os.path.basename(f) for f in files]
        self.assertIn("inner.blh", file_names)
        self.assertIn("outer.blh", file_names)
        self.assertIn("main.blcpp", file_names)

    def test_pragma_once(self):
        """Same file is only included once"""
        shared = Path(self.temp_dir) / "shared.blh"
        shared.write_text("#pragma once\nint shared = 1\n")
        
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('#include "shared.blh"\n#include "shared.blh"\nint main():\n    return shared\n')
        
        lines, line_map = expand_blh_includes(str(source))
        
        # shared.blh content should appear only once
        content = ''.join(lines)
        self.assertEqual(content.count("int shared = 1"), 1)

    def test_diamond_include(self):
        """Diamond include pattern works correctly"""
        # A includes B and C, both B and C include D
        d = Path(self.temp_dir) / "d.blh"
        d.write_text("#pragma once\nint d = 4\n")
        
        b = Path(self.temp_dir) / "b.blh"
        b.write_text('#pragma once\n#include "d.blh"\nint b = 2\n')
        
        c = Path(self.temp_dir) / "c.blh"
        c.write_text('#pragma once\n#include "d.blh"\nint c = 3\n')
        
        a = Path(self.temp_dir) / "a.blcpp"
        a.write_text('#include "b.blh"\n#include "c.blh"\nint main():\n    return b + c + d\n')
        
        lines, line_map = expand_blh_includes(str(a))
        
        # d.blh content should appear only once
        content = ''.join(lines)
        self.assertEqual(content.count("int d = 4"), 1)

    def test_regular_h_not_expanded(self):
        """Regular .h includes are not expanded"""
        header = Path(self.temp_dir) / "regular.h"
        header.write_text("int regular = 1;\n")
        
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('#include "regular.h"\nint main():\n    return regular\n')
        
        lines, line_map = expand_blh_includes(str(source))
        
        # The #include "regular.h" should be preserved
        content = ''.join(lines)
        self.assertIn('#include "regular.h"', content)
        
        # But the content of regular.h should NOT be included
        self.assertNotIn("int regular = 1", content)

    def test_missing_header_preserved(self):
        """Missing .blh include is preserved (compiler will report error)"""
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('#include "missing.blh"\nint main():\n    return 0\n')
        
        lines, line_map = expand_blh_includes(str(source))
        
        # The include should be preserved
        content = ''.join(lines)
        self.assertIn('#include "missing.blh"', content)


class TestSourceLocationMapper(unittest.TestCase):
    """Tests for SourceLocationMapper"""

    def test_simple_mapping(self):
        """Test basic line mapping"""
        # Simulate: expanded file has 5 lines
        # Lines 1-2 from header.blh, lines 3-5 from main.blcpp
        blh_line_map = {
            1: ("header.blh", 1),
            2: ("header.blh", 2),
            3: ("main.blcpp", 2),
            4: ("main.blcpp", 3),
            5: ("main.blcpp", 4),
        }
        
        # Simulate: transpilation adds closing braces
        # transpiled line 1 -> expanded line 1
        # transpiled line 2 -> expanded line 2
        # transpiled line 3 -> expanded line 2 (closing brace)
        # etc.
        class MockTranspileMapper:
            def get_source_line(self, line):
                mapping = {1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 5, 7: 5}
                return mapping.get(line, line)
        
        mapper = SourceLocationMapper(blh_line_map, MockTranspileMapper())
        
        # Line 1 should map to header.blh:1
        file, line = mapper.get_source_location(1)
        self.assertEqual(file, "header.blh")
        self.assertEqual(line, 1)
        
        # Line 3 (closing brace) should map to header.blh:2
        file, line = mapper.get_source_location(3)
        self.assertEqual(file, "header.blh")
        self.assertEqual(line, 2)
        
        # Line 4 should map to main.blcpp:2
        file, line = mapper.get_source_location(4)
        self.assertEqual(file, "main.blcpp")
        self.assertEqual(line, 2)


class TestEndToEnd(unittest.TestCase):
    """End-to-end tests for .blh expansion + transpilation"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='blcc_test_')
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_full_pipeline(self):
        """Test complete expansion + transpilation"""
        header = Path(self.temp_dir) / "utils.blh"
        header.write_text("#pragma once\n\nint add(int a, int b):\n    return a + b\n")
        
        source = Path(self.temp_dir) / "main.blcpp"
        source.write_text('#include "utils.blh"\n\nint main():\n    return add(1, 2)\n')
        
        # Expand
        lines, blh_line_map = expand_blh_includes(str(source))
        
        # Transpile
        compiler = MappingCompiler(lines)
        output = compiler.compile()
        
        # Verify output has braces
        self.assertIn("int add(int a, int b) {", output)
        self.assertIn("int main() {", output)
        self.assertIn("return a + b;", output)
        
        # Create mapper
        mapper = SourceLocationMapper(blh_line_map, compiler.line_mapper)
        
        # Find a line in the output that should map to utils.blh
        # The "return a + b" line should map to utils.blh:4
        output_lines = output.split('\n')
        for i, line in enumerate(output_lines, 1):
            if "return a + b" in line:
                file, src_line = mapper.get_source_location(i)
                self.assertIn("utils.blh", file)
                break


if __name__ == '__main__':
    unittest.main(verbosity=2)
