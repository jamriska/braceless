#!/usr/bin/env python3
"""
Braceless C++ Compiler (blcc)

Converts Python-style indented C++ to regular braced C++.
"""

import sys
import os
import re
import subprocess
import tempfile
import shutil
from typing import List, Tuple, Optional, NamedTuple, Set, Dict, Callable
from enum import Enum, auto
from dataclasses import dataclass
import clang.cindex


class TokenKind(Enum):
    """Token types returned by the tokenizer"""
    KEYWORD = auto()
    IDENTIFIER = auto()
    LITERAL = auto()
    PUNCTUATION = auto()
    COMMENT = auto()
    UNKNOWN = auto()


@dataclass
class Token:
    """A single token from the source code"""
    kind: TokenKind
    spelling: str
    line: int      # 1-based line number
    column: int    # 1-based column number
    
    def __repr__(self):
        return f"Token({self.kind.name}, {self.spelling!r}, L{self.line}:{self.column})"


def _clang_kind_to_token_kind(clang_kind) -> TokenKind:
    """Convert clang token kind to our TokenKind enum"""
    kind_name = clang_kind.name
    if kind_name == 'KEYWORD':
        return TokenKind.KEYWORD
    elif kind_name == 'IDENTIFIER':
        return TokenKind.IDENTIFIER
    elif kind_name == 'LITERAL':
        return TokenKind.LITERAL
    elif kind_name == 'PUNCTUATION':
        return TokenKind.PUNCTUATION
    elif kind_name == 'COMMENT':
        return TokenKind.COMMENT
    else:
        return TokenKind.UNKNOWN


def tokenize(source: str) -> List[Token]:
    """
    Tokenize braceless C++ source code.
    
    Args:
        source: The source code string to tokenize
        
    Returns:
        List of Token objects
    """
    # Create index and parse as C++ using unsaved_files
    index = clang.cindex.Index.create()
    
    # Parse the source as a virtual .cpp file
    tu = index.parse(
        'source.cpp',
        args=['-x', 'c++', '-std=c++17'],
        unsaved_files=[('source.cpp', source)],
        options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
    )
    
    # Extract tokens
    tokens = []
    for clang_token in tu.get_tokens(extent=tu.cursor.extent):
        token = Token(
            kind=_clang_kind_to_token_kind(clang_token.kind),
            spelling=clang_token.spelling,
            line=clang_token.location.line,
            column=clang_token.location.column
        )
        tokens.append(token)
    
    return tokens


def tokens_on_line(tokens: List[Token], line: int) -> List[Token]:
    """Get all tokens on a specific line"""
    return [t for t in tokens if t.line == line]


def meaningful_tokens(tokens: List[Token]) -> List[Token]:
    """Filter out comment tokens"""
    return [t for t in tokens if t.kind != TokenKind.COMMENT]


def paren_balance(tokens: List[Token]) -> int:
    """
    Calculate the balance of parentheses/brackets.
    Positive = more opens than closes.
    Note: Does NOT count braces {} as they're typically block delimiters, not expression grouping.
    """
    opens = sum(1 for t in tokens if t.kind == TokenKind.PUNCTUATION and t.spelling in '([')
    closes = sum(1 for t in tokens if t.kind == TokenKind.PUNCTUATION and t.spelling in ')]')
    return opens - closes


def has_keyword(tokens: List[Token], keyword: str) -> bool:
    """Check if tokens contain a specific keyword"""
    return any(t.kind == TokenKind.KEYWORD and t.spelling == keyword for t in tokens)


def first_keyword(tokens: List[Token]) -> Optional[Token]:
    """Get the first keyword token, if any"""
    for t in tokens:
        if t.kind == TokenKind.KEYWORD:
            return t
    return None


def has_lambda_pattern(tokens: List[Token]) -> bool:
    """
    Check if tokens contain a lambda pattern: [...](...) or [...]
    
    Distinguishes lambdas from array subscripts by checking if [ follows an identifier
    (array subscript: arr[i]) vs starts fresh (lambda: [](...) or [&](...)).
    """
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.kind == TokenKind.PUNCTUATION and t.spelling == '[':
            # Skip if this is array subscript ([ immediately after identifier/literal/])
            if i > 0:
                prev = tokens[i - 1]
                if prev.kind in (TokenKind.IDENTIFIER, TokenKind.LITERAL) or prev.spelling in (']', ')'):
                    # This is array subscript, not lambda
                    i += 1
                    continue
            
            # Find matching ]
            bracket_depth = 1
            j = i + 1
            while j < len(tokens) and bracket_depth > 0:
                if tokens[j].spelling == '[':
                    bracket_depth += 1
                elif tokens[j].spelling == ']':
                    bracket_depth -= 1
                j += 1
            
            if bracket_depth == 0:
                # Found matching ] at position j-1
                # Check if followed by ( for lambda with params
                if j < len(tokens) and tokens[j].spelling == '(':
                    return True
                # Also consider [&], [=], [] as lambda captures even without ()
                # These are lambdas if the capture is simple
                capture_tokens = tokens[i+1:j-1]
                if len(capture_tokens) <= 1:  # [], [&], [=], [x]
                    return True
        i += 1
    return False


class LogicalLine:
    """
    A logical line represents one or more physical lines that form a single statement.
    
    Continuations are merged automatically based on:
    - Unmatched parentheses/brackets/braces
    - Continuation operators at end of line
    - Continuation starters at beginning of next line
    """
    
    def __init__(self, start_line: int, raw_lines: List[str], tokens: List[Token]):
        self.start_line = start_line  # 1-based line number
        self.raw_lines = raw_lines    # Original source lines (for whitespace preservation)
        self.tokens = tokens          # All tokens in this logical line
        self._meaningful = None       # Cached meaningful tokens
    
    @property
    def meaningful(self) -> List[Token]:
        """Get non-comment tokens"""
        if self._meaningful is None:
            self._meaningful = [t for t in self.tokens if t.kind != TokenKind.COMMENT]
        return self._meaningful
    
    @property
    def indent(self) -> int:
        """
        Get the visual indent level of this logical line.
        Computed from the first token's column, converting tabs to 4 spaces.
        """
        if not self.raw_lines:
            return 0
        
        first_line = self.raw_lines[0]
        indent = 0
        for ch in first_line:
            if ch == ' ':
                indent += 1
            elif ch == '\t':
                indent += 4
            else:
                break
        return indent
    
    @property
    def leading_ws(self) -> str:
        """Get the original leading whitespace from the first line"""
        if not self.raw_lines:
            return ''
        first_line = self.raw_lines[0]
        return first_line[:len(first_line) - len(first_line.lstrip(' \t'))]
    
    def is_blank(self) -> bool:
        """Check if this is a blank line (no tokens)"""
        return len(self.tokens) == 0
    
    def is_comment_only(self) -> bool:
        """Check if this line contains only comments"""
        return len(self.tokens) > 0 and len(self.meaningful) == 0
    
    def is_blank_or_comment(self) -> bool:
        """Check if this is blank or comment-only"""
        return self.is_blank() or self.is_comment_only()
    
    def ends_with_colon(self) -> bool:
        """Check if the last meaningful token is a colon"""
        if not self.meaningful:
            return False
        return self.meaningful[-1].spelling == ':'
    
    def ends_with_brace(self) -> bool:
        """Check if the last meaningful token is an opening brace"""
        if not self.meaningful:
            return False
        return self.meaningful[-1].spelling == '{'
    
    def is_block_start(self) -> bool:
        """
        Check if this line starts a braceless block (ends with : but not case/default/access).
        """
        if not self.ends_with_colon():
            return False
        
        m = self.meaningful
        if len(m) < 2:
            return True  # Just ":" alone starts a block
        
        # Check for case/default (these keep the colon)
        # case VALUE: or default:
        prev = m[-2]
        if prev.kind == TokenKind.KEYWORD and prev.spelling in ('default',):
            return False
        if prev.kind == TokenKind.LITERAL:
            # Could be "case VALUE:" - check if 'case' appears before
            if any(t.kind == TokenKind.KEYWORD and t.spelling == 'case' for t in m[:-2]):
                return False
        if prev.kind == TokenKind.KEYWORD and prev.spelling == 'case':
            return False
            
        # Check for access specifiers (public/private/protected:)
        if len(m) == 2 and prev.kind == TokenKind.KEYWORD and prev.spelling in ('public', 'private', 'protected'):
            return False
        
        return True
    
    def is_access_specifier(self) -> bool:
        """Check if this is an access specifier (public:/private:/protected:)"""
        m = self.meaningful
        if len(m) != 2:
            return False
        return (m[0].kind == TokenKind.KEYWORD and 
                m[0].spelling in ('public', 'private', 'protected') and
                m[1].spelling == ':')
    
    def is_case_or_default(self) -> bool:
        """Check if this is a case or default label"""
        if not self.ends_with_colon():
            return False
        m = self.meaningful
        if not m:
            return False
        # default:
        if m[0].kind == TokenKind.KEYWORD and m[0].spelling == 'default':
            return True
        # case VALUE:
        if m[0].kind == TokenKind.KEYWORD and m[0].spelling == 'case':
            return True
        return False
    
    def __repr__(self):
        return f"LogicalLine(L{self.start_line}, {len(self.raw_lines)} lines, {len(self.tokens)} tokens)"


# Continuation operators - if line ends with these, it continues to next line
# Note: '{' is NOT included because it opens blocks; continuation for initializers
# is handled by paren_balance (unmatched '{')
CONTINUATION_OPS = {'+', '-', '*', '/', '%', '&', '|', '^', '=', '<', '>', ',', '(', '[',
                    '&&', '||', '==', '!=', '<=', '>=', '+=', '-=', '*=', '/=', '%=',
                    '&=', '|=', '^=', '<<=', '>>=', '->', '.', '::'}

# Continuation starters - if next line starts with these, previous line continues
# Note: '}' is NOT included because it typically closes a block, not continues an expression
CONTINUATION_STARTERS = {'.', ',', ')', ']', '?', ':'}


def _is_continuation_end(tokens: List[Token]) -> bool:
    """Check if tokens end with a continuation operator or unmatched parens"""
    m = meaningful_tokens(tokens)
    if not m:
        return False
    
    # Preprocessor directives never continue (they end at newline)
    if m[0].spelling == '#':
        return False
    
    last = m[-1]
    
    # Check for ++ or -- (not continuation)
    if last.spelling in ('++', '--'):
        return False
    
    # Unmatched parens/brackets/braces means continuation
    if paren_balance(tokens) > 0:
        return True
    
    # Continuation operators
    if last.kind == TokenKind.PUNCTUATION and last.spelling in CONTINUATION_OPS:
        return True
    
    # Special case: 'for' loop without parens and without colon continues
    # This handles multiline for conditions like:
    #   for int i = 0;
    #       i < 10;
    #       i++:
    # Note: We only do this for 'for' because it uses semicolons internally.
    # If the for already has parens like 'for (int i=0; ...) expr', don't continue.
    first = m[0]
    if first.kind == TokenKind.KEYWORD and first.spelling == 'for':
        # Check if there's a ( right after 'for' - if so, it's traditional syntax
        if len(m) > 1 and m[1].spelling == '(':
            # Traditional for with parens - don't continue
            return False
        # Check if line ends with : or { - if not, it continues
        if last.spelling not in (':', '{'):
            return True
    
    return False


def _is_continuation_start(tokens: List[Token]) -> bool:
    """Check if tokens start with a continuation character"""
    m = meaningful_tokens(tokens)
    if not m:
        return False
    
    first = m[0]
    if first.kind == TokenKind.PUNCTUATION and first.spelling in CONTINUATION_STARTERS:
        return True
    
    # String literal at start of line continues previous string (string concatenation)
    if first.kind == TokenKind.LITERAL and first.spelling.startswith('"'):
        return True
    
    return False


def group_logical_lines(source: str, tokens: List[Token]) -> List[LogicalLine]:
    """
    Group tokens into logical lines, merging continuations.
    
    Args:
        source: Original source code (for preserving whitespace)
        tokens: All tokens from the source
        
    Returns:
        List of LogicalLine objects
    """
    lines = source.splitlines()
    if not lines:
        return []
    
    # Build a map of line number -> tokens on that line
    line_tokens = {}
    for t in tokens:
        if t.line not in line_tokens:
            line_tokens[t.line] = []
        line_tokens[t.line].append(t)
    
    logical_lines = []
    i = 0
    
    while i < len(lines):
        line_num = i + 1  # 1-based
        current_tokens = line_tokens.get(line_num, [])
        raw_lines = [lines[i]]
        all_tokens = list(current_tokens)
        
        # Check if this line continues to the next
        cumulative_balance = paren_balance(all_tokens)
        
        while i + 1 < len(lines):
            next_line_num = i + 2  # 1-based
            next_tokens = line_tokens.get(next_line_num, [])
            
            # Continue if:
            # 1. Cumulative paren balance > 0
            # 2. Current line ends with continuation operator
            # 3. Next line starts with continuation character
            should_continue = False
            
            if cumulative_balance > 0:
                should_continue = True
            elif _is_continuation_end(all_tokens):
                should_continue = True
            elif _is_continuation_start(next_tokens):
                should_continue = True
            
            if not should_continue:
                break
            
            # Merge the next line
            i += 1
            raw_lines.append(lines[i])
            all_tokens.extend(next_tokens)
            cumulative_balance = paren_balance(all_tokens)
        
        logical_lines.append(LogicalLine(line_num, raw_lines, all_tokens))
        i += 1
    
    return logical_lines


class BlockType(Enum):
    NORMAL = auto()
    CLASS = auto()
    STRUCT = auto()
    ENUM = auto()
    UNION = auto()
    SWITCH = auto()
    LAMBDA = auto()
    REGULAR_BRACE = auto()  # Regular C++ braces (don't output closing brace)
    DO = auto()  # do-while loop (closing brace merges with while)


class TokenCompiler:
    """
    Token-based Braceless C++ Compiler.
    
    Processes logical lines (statements) rather than physical lines,
    eliminating the need for complex multiline state tracking.
    """
    
    def __init__(self, lines: List[str]):
        # Join lines into source, preserving original lines for whitespace
        self.source = '\n'.join(line.rstrip('\n\r') for line in lines)
        self.lines = [line.rstrip('\n\r') for line in lines]
        
        # Tokenize the entire source
        self.tokens = tokenize(self.source)
        
        # Group into logical lines
        self.logical_lines = group_logical_lines(self.source, self.tokens)
        
        # State tracking
        self.indent_stack = [0]
        self.block_type_stack = [BlockType.NORMAL]
        self.whitespace_stack = ['']  # Track whitespace for closing braces
        
        # Output
        self.output = []
        
        # Pending blank lines (for proper placement around closing braces)
        self.pending_blank_lines = []
        
        # Flag for do-while handling
        self._do_while_handled = False
    
    def compile(self) -> str:
        """Compile the braceless C++ to regular C++"""
        for ll in self.logical_lines:
            self._process_logical_line(ll)
        
        # Close any remaining blocks
        saved_blank_lines = self.pending_blank_lines
        self.pending_blank_lines = []
        
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
            closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
            self._output_closing_brace(block_type, closing_ws)
        
        # Output any remaining blank lines
        if saved_blank_lines:
            buffered = []
            for item in saved_blank_lines:
                if isinstance(item, tuple):
                    raw = item[0]
                    src_line = item[2] if len(item) >= 3 else 0
                    buffered.append((raw, src_line))
                else:
                    buffered.append((item, 0))
            self._emit_buffered_lines(buffered)
        
        return '\n'.join(self.output) + '\n'
    
    def _buffer_blank_or_comment(self, raw_line: str, indent: int, source_line: int):
        """Buffer a blank or comment line. Can be overridden for line tracking.
        
        Args:
            raw_line: The raw line content
            indent: The indent level
            source_line: The source line number (1-based)
        """
        self.pending_blank_lines.append((raw_line, indent, source_line))
    
    def _process_logical_line(self, ll: LogicalLine):
        """Process a single logical line"""
        
        # Handle blank lines
        if ll.is_blank():
            # Buffer blank lines with their indent info for later placement
            raw_line = ll.raw_lines[0] if ll.raw_lines else ''
            self._buffer_blank_or_comment(raw_line, ll.indent, ll.start_line)
            return
        
        # Handle comment-only lines
        if ll.is_comment_only():
            # Buffer comments along with blank lines for proper placement during dedent
            for i, raw_line in enumerate(ll.raw_lines):
                self._buffer_blank_or_comment(raw_line, ll.indent, ll.start_line + i)
            return
        
        # Handle dedenting (closing blocks)
        if ll.indent < self.indent_stack[-1]:
            # Check if this is an access specifier - don't close class/struct for those
            if ll.is_access_specifier():
                # Partition blank lines: those inside block vs those after
                inside_blanks = []
                after_blanks = []
                for item in self.pending_blank_lines:
                    raw, indent, src_line = item if len(item) == 3 else (item[0], item[1], 0)
                    if indent < ll.indent:
                        inside_blanks.append((raw, src_line))
                    else:
                        after_blanks.append((raw, src_line))
                self.pending_blank_lines = []
                
                # Output inside blanks first
                self._emit_buffered_lines(inside_blanks)
                self._close_to_class_level()
                self._emit_buffered_lines(after_blanks)
            else:
                # Normal dedent - close blocks
                # Partition blank lines: inside block (before }) or after block
                # A blank line goes inside if:
                # 1. Its indent is at the block's content level or higher, OR
                # 2. It's between block content and the dedented line (indent < ll.indent)
                inside_blanks = []
                after_blanks = []
                block_content_indent = self.indent_stack[-1] if len(self.indent_stack) > 1 else 0
                for item in self.pending_blank_lines:
                    raw, indent, src_line = item if len(item) == 3 else (item[0], item[1], 0)
                    # Either at block level or before the dedented line
                    if indent >= block_content_indent or indent < ll.indent:
                        inside_blanks.append((raw, src_line))
                    else:
                        after_blanks.append((raw, src_line))
                self.pending_blank_lines = []
                
                # Output inside blanks before closing brace
                self._emit_buffered_lines(inside_blanks)
                
                # Check if this is a while clause for do-while
                is_do_while_clause = False
                m = ll.meaningful
                if (m and m[0].kind == TokenKind.KEYWORD and m[0].spelling == 'while' and 
                    not ll.ends_with_colon()):
                    # Check if we're closing a DO block
                    if len(self.block_type_stack) > 1 and self.block_type_stack[-1] == BlockType.DO:
                        is_do_while_clause = True
                
                while len(self.indent_stack) > 1 and self.indent_stack[-1] > ll.indent:
                    self.indent_stack.pop()
                    block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
                    closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
                    if block_type != BlockType.REGULAR_BRACE:
                        if block_type == BlockType.DO and is_do_while_clause:
                            # For do-while, output "} while (condition);" merged
                            # Use original line text for proper spacing
                            raw_line = ll.raw_lines[0] if ll.raw_lines else ''
                            while_clause = raw_line.strip()
                            
                            # Check if condition already has parens
                            # Extract condition after 'while'
                            while_idx = while_clause.find('while')
                            if while_idx >= 0:
                                after_while = while_clause[while_idx + 5:].strip()
                                # Remove trailing semicolon if present
                                if after_while.endswith(';'):
                                    after_while = after_while[:-1].strip()
                                # Wrap in parens if not already
                                if not (after_while.startswith('(') and after_while.endswith(')')):
                                    while_clause = f"while ({after_while})"
                                else:
                                    while_clause = f"while {after_while}"
                            
                            self.output.append(f"{closing_ws}}} {while_clause};")
                            # Mark that we've handled this line
                            self._do_while_handled = True
                        else:
                            self._output_closing_brace(block_type, closing_ws)
                
                # Output after blanks after closing braces
                self._emit_buffered_lines(after_blanks)
        
        # Check if we already handled this line as part of do-while
        if hasattr(self, '_do_while_handled') and self._do_while_handled:
            self._do_while_handled = False
            return
        
        # Check if this is else/catch that should merge with previous closing brace
        is_else_catch = self._is_else_or_catch(ll)
        
        # Flush pending blank lines (unless else/catch)
        if not is_else_catch:
            self._flush_blank_lines()
        
        # Handle access specifiers (public:/private:/protected:)
        if ll.is_access_specifier():
            self._flush_blank_lines()
            self._emit_raw_lines(ll)
            return
        
        # Handle case/default labels
        if ll.is_case_or_default():
            self._emit_raw_lines(ll)
            return
        
        # Handle regular closing brace
        if self._is_closing_brace(ll):
            self._handle_closing_brace(ll)
            return
        
        # Handle line ending with opening brace (regular C++ brace)
        if ll.ends_with_brace():
            self._handle_regular_brace(ll)
            return
        
        # Handle block start (ends with colon)
        if ll.is_block_start():
            self._handle_block_start(ll)
            return
        
        # Regular statement - add semicolon if needed
        self._handle_statement(ll)
    
    def _is_else_or_catch(self, ll: LogicalLine) -> bool:
        """Check if this line is an else or catch clause"""
        m = ll.meaningful
        if not m:
            return False
        first = m[0]
        return first.kind == TokenKind.KEYWORD and first.spelling in ('else', 'catch')
    
    def _is_closing_brace(self, ll: LogicalLine) -> bool:
        """Check if this is just a closing brace"""
        m = ll.meaningful
        return len(m) == 1 and m[0].spelling == '}'
    
    def _close_to_class_level(self):
        """Close inner blocks but keep class/struct open (for access specifiers)"""
        while len(self.indent_stack) > 1:
            if self.block_type_stack[-1] in (BlockType.CLASS, BlockType.STRUCT):
                break
            self.indent_stack.pop()
            block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
            closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
            if block_type != BlockType.REGULAR_BRACE:
                self._output_closing_brace(block_type, closing_ws)
    
    def _detect_block_type(self, ll: LogicalLine) -> BlockType:
        """Detect what type of block is starting based on tokens"""
        keywords = {t.spelling for t in ll.tokens if t.kind == TokenKind.KEYWORD}
        
        # Check for do (do-while loop)
        m = ll.meaningful
        if m and m[0].kind == TokenKind.KEYWORD and m[0].spelling == 'do':
            return BlockType.DO
        
        # Check for enum first (before class) to handle "enum class"
        if 'enum' in keywords:
            return BlockType.ENUM
        if 'class' in keywords:
            return BlockType.CLASS
        if 'struct' in keywords:
            return BlockType.STRUCT
        if 'union' in keywords:
            return BlockType.UNION
        if 'switch' in keywords:
            return BlockType.SWITCH
        
        # Lambda detection
        if has_lambda_pattern(ll.tokens):
            return BlockType.LAMBDA
        
        return BlockType.NORMAL
    
    def _wrap_condition_if_needed(self, ll: LogicalLine) -> str:
        """
        Wrap condition in parentheses if it's a control structure without parens.
        Returns the transformed line content (without the trailing colon, with parens).
        Preserves original whitespace from source and comments.
        """
        m = ll.meaningful
        if not m:
            return ll.leading_ws
        
        # Check if first token is a control keyword
        first = m[0]
        control_keywords = {'if', 'for', 'while', 'switch'}
        
        keyword = None
        keyword_end_idx = 0
        
        if first.kind == TokenKind.KEYWORD:
            if first.spelling in control_keywords:
                keyword = first.spelling
                keyword_end_idx = 1
            elif first.spelling == 'else' and len(m) > 1:
                second = m[1]
                if second.kind == TokenKind.KEYWORD and second.spelling == 'if':
                    keyword = 'else if'
                    keyword_end_idx = 2
        
        if not keyword:
            # Not a control structure - use original line without colon
            return self._strip_trailing_colon(ll)
        
        # Check if condition is already fully wrapped in parentheses
        if keyword_end_idx < len(m) and m[keyword_end_idx].spelling == '(':
            # Check if the FIRST opening paren matches the LAST closing paren (right before ':')
            # This distinguishes "if (a && b):" from "if (a) && b:"
            # We track when the initial paren is closed, not just any paren reaching 0
            paren_depth = 0
            first_paren_closes_at_end = False
            for i in range(keyword_end_idx, len(m) - 1):  # -1 to exclude ':'
                if m[i].spelling == '(':
                    paren_depth += 1
                elif m[i].spelling == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        # The initial paren just closed
                        if i == len(m) - 2:
                            # And it closes right before :, so fully wrapped
                            first_paren_closes_at_end = True
                        # Either way, break here since the initial paren is now closed
                        break
            if first_paren_closes_at_end:
                # Already has parens around entire condition - just strip the colon
                return self._strip_trailing_colon(ll)
        
        # Need to wrap the condition in parentheses
        colon_token = m[-1]  # Should be ':'
        colon_line = colon_token.line  # 1-based line number
        
        # Handle multiline case
        if len(ll.raw_lines) > 1 or colon_line > ll.start_line:
            # Multiline condition - join all lines and extract condition
            # Build full content from raw lines
            all_content = '\n'.join(ll.raw_lines)
            
            # Find keyword position in first line
            first_line = ll.raw_lines[0]
            keyword_token = m[keyword_end_idx - 1]
            keyword_end_col = keyword_token.column + len(keyword_token.spelling) - 1
            
            # Find colon position in last line
            colon_line_idx = colon_token.line - ll.start_line  # 0-based index
            colon_col = colon_token.column - 1  # 0-based
            
            # Extract content after keyword from first line
            first_after_keyword = first_line[keyword_end_col:]
            
            # Extract content before colon from last line
            if colon_line_idx < len(ll.raw_lines):
                last_line = ll.raw_lines[colon_line_idx]
                last_before_colon = last_line[:colon_col]
            else:
                last_before_colon = ''
            
            # Build condition: first line content + middle lines + last line content
            if colon_line_idx == 0:
                # Single line (shouldn't happen here, but handle it)
                condition = first_line[keyword_end_col:colon_col].strip()
            else:
                # Preserve original whitespace within lines
                parts = [first_after_keyword]
                for i in range(1, colon_line_idx):
                    parts.append(ll.raw_lines[i])
                parts.append(last_before_colon)
                condition = '\n'.join(parts)
            
            # For multiline, output with newlines preserved but add parens
            # Strip leading whitespace from condition but preserve internal whitespace
            result = f"{ll.leading_ws}{keyword} ({condition.lstrip()})"
            return result
        
        # Single line case
        first_line = ll.raw_lines[0] if ll.raw_lines else ''
        
        # Find keyword end position in source
        keyword_token = m[keyword_end_idx - 1]
        keyword_end_col = keyword_token.column + len(keyword_token.spelling) - 1
        
        # Find colon position
        colon_col = colon_token.column - 1  # 0-based
        
        # Extract condition from source (between keyword and colon)
        condition = first_line[keyword_end_col:colon_col].strip()
        
        # Get comment text after colon (if any)
        comment_text = ''
        after_colon = first_line[colon_col + 1:] if colon_col + 1 < len(first_line) else ''
        if after_colon.strip():
            comment_text = after_colon
        
        result = f"{ll.leading_ws}{keyword} ({condition})"
        if comment_text:
            result += comment_text
        return result
    
    def _strip_trailing_colon(self, ll: LogicalLine) -> str:
        """Remove the trailing colon from the logical line, preserving whitespace and comments"""
        # Find the colon token and get its position
        m = ll.meaningful
        if not m or m[-1].spelling != ':':
            return '\n'.join(ll.raw_lines)
        
        colon_token = m[-1]
        colon_line = colon_token.line - ll.start_line  # 0-based index into raw_lines
        colon_col = colon_token.column - 1  # 0-based column
        
        if len(ll.raw_lines) == 1:
            line = ll.raw_lines[0]
            # Remove colon but keep everything after it (comments)
            before_colon = line[:colon_col]
            after_colon = line[colon_col + 1:]  # Skip the colon
            return before_colon.rstrip() + after_colon
        else:
            # Multiline - strip colon from the line containing it
            lines = list(ll.raw_lines)
            if colon_line < len(lines):
                line = lines[colon_line]
                before_colon = line[:colon_col]
                after_colon = line[colon_col + 1:]
                lines[colon_line] = before_colon.rstrip() + after_colon
            return '\n'.join(lines)
    
    def _wrap_condition_for_brace(self, ll: LogicalLine) -> Optional[str]:
        """
        Wrap condition in parentheses for control structures ending with {.
        Returns the transformed line if wrapping was needed, None otherwise.
        """
        m = ll.meaningful
        if not m or m[-1].spelling != '{':
            return None
        
        # Check if first token is a control keyword
        first = m[0]
        control_keywords = {'if', 'for', 'while', 'switch'}
        
        keyword = None
        keyword_end_idx = 0
        
        if first.kind == TokenKind.KEYWORD:
            if first.spelling in control_keywords:
                keyword = first.spelling
                keyword_end_idx = 1
            elif first.spelling == 'else' and len(m) > 1:
                second = m[1]
                if second.kind == TokenKind.KEYWORD and second.spelling == 'if':
                    keyword = 'else if'
                    keyword_end_idx = 2
        
        if not keyword:
            return None
        
        # Check if condition is already wrapped in parentheses
        if keyword_end_idx < len(m) - 1 and m[keyword_end_idx].spelling == '(':
            # Check if the opening paren matches a closing paren right before '{'
            paren_depth = 0
            for i in range(keyword_end_idx, len(m) - 1):  # -1 to exclude '{'
                if m[i].spelling == '(':
                    paren_depth += 1
                elif m[i].spelling == ')':
                    paren_depth -= 1
                    if paren_depth == 0 and i == len(m) - 2:
                        # Already fully wrapped
                        return None
        
        # Need to wrap the condition in parentheses
        raw_line = ll.raw_lines[0] if ll.raw_lines else ''
        
        # Find positions in the raw line
        keyword_token = m[keyword_end_idx - 1]
        keyword_end_col = keyword_token.column + len(keyword_token.spelling) - 1
        
        brace_token = m[-1]
        brace_col = brace_token.column - 1  # 0-based
        
        # Extract condition from source (between keyword and brace)
        condition = raw_line[keyword_end_col:brace_col].strip()
        
        # Get comment text after brace if any
        comment_text = ''
        after_brace = raw_line[brace_col + 1:] if brace_col + 1 < len(raw_line) else ''
        comment_tokens = [t for t in ll.tokens if t.kind == TokenKind.COMMENT and t.line == ll.start_line]
        if comment_tokens:
            comment_col = comment_tokens[0].column - 1
            comment_text = raw_line[comment_col:]
        
        result = f"{ll.leading_ws}{keyword} ({condition}) {{"
        if comment_text:
            result += ' ' + comment_text
        elif after_brace.strip():
            result += after_brace
        return result
    
    def _handle_block_start(self, ll: LogicalLine):
        """Handle a line that starts a braceless block (ends with :)"""
        block_type = self._detect_block_type(ll)
        
        # Get transformed content (colon removed, condition wrapped if needed)
        content = self._wrap_condition_if_needed(ll)
        
        # Check if there's a comment token on the first line
        comment_part = ''
        before_comment = content
        comment_tokens = [t for t in ll.tokens if t.kind == TokenKind.COMMENT and t.line == ll.start_line]
        if comment_tokens:
            # There's a comment - check if content already contains it
            # by seeing if the comment text appears in content
            first_comment = comment_tokens[0]
            raw_line = ll.raw_lines[0] if ll.raw_lines else ''
            comment_col = first_comment.column - 1
            comment_text = raw_line[comment_col:]
            
            if comment_text in content:
                # Content already has the comment - extract it
                idx = content.find(comment_text)
                before_comment = content[:idx].rstrip()
                comment_part = ' ' + comment_text
            else:
                # Content doesn't have the comment - add it
                comment_part = ' ' + comment_text
        
        # Capture any trailing whitespace from before_comment to place after the brace
        trailing_ws = ''
        stripped_before = before_comment.rstrip()
        if len(before_comment) > len(stripped_before):
            trailing_ws = before_comment[len(stripped_before):]
        before_comment = stripped_before
        
        # Check for else/catch - merge with previous closing brace
        if self._is_else_or_catch(ll):
            if self.output and self.output[-1].strip() == '}':
                self.output.pop()
                self.output.append(f"{ll.leading_ws}}} {before_comment.lstrip()} {{{trailing_ws}{comment_part}")
                self._flush_blank_lines()
            else:
                self._flush_blank_lines()
                self.output.append(f"{before_comment} {{{trailing_ws}{comment_part}")
        else:
            # Regular block start
            self.output.append(f"{before_comment} {{{trailing_ws}{comment_part}")
        
        # Track the new block
        self._push_block(ll, block_type)
    
    def _handle_regular_brace(self, ll: LogicalLine):
        """Handle a line that ends with opening brace (regular C++ syntax)"""
        # Check for else/catch with regular brace
        if self._is_else_or_catch(ll):
            # Use original raw line to preserve exact spacing (e.g., std::exception& vs std :: exception &)
            raw_content = ll.raw_lines[0].strip() if ll.raw_lines else ''
            if self.output and self.output[-1].strip() == '}':
                self.output.pop()
                self.output.append(f"{ll.leading_ws}}} {raw_content}")
            else:
                self.output.append(f"{ll.leading_ws}{raw_content}")
        else:
            # Check if this is a control statement that needs parens around condition
            wrapped_line = self._wrap_condition_for_brace(ll)
            if wrapped_line is not None:
                self.output.append(wrapped_line)
            else:
                # Output lines as-is
                self._emit_raw_lines(ll)
        
        # Track the regular brace block
        self._push_block(ll, BlockType.REGULAR_BRACE)
    
    def _handle_closing_brace(self, ll: LogicalLine):
        """Handle a standalone closing brace"""
        # Pop from stack if appropriate
        if len(self.indent_stack) > 1 and ll.indent < self.indent_stack[-1]:
            self.indent_stack.pop()
            if len(self.block_type_stack) > 1:
                self.block_type_stack.pop()
            if len(self.whitespace_stack) > 1:
                self.whitespace_stack.pop()
        
        self._emit_raw_lines(ll)
    
    def _transform_inline_braceless_lambdas(self, lines: List[str]) -> List[str]:
        """
        Transform braceless lambda patterns within raw lines.
        
        Detects patterns like [...](...): followed by indented body lines
        and converts them to braced form.
        """
        if len(lines) <= 1:
            return lines
        
        result = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.rstrip()
            
            # Check if line ends with ): or ]: (lambda pattern with colon)
            # Make sure there's a [ somewhere before the : to confirm it's a lambda
            if stripped.endswith(':') and '[' in stripped:
                # Check if this looks like a lambda: [...] or [...](...)
                # Find the last ] before the :
                colon_pos = len(stripped) - 1
                bracket_pos = stripped.rfind(']')
                
                if bracket_pos >= 0:
                    between = stripped[bracket_pos + 1:colon_pos].strip()
                    # Valid lambda patterns: ] followed by : or ](...) followed by :
                    if between == '' or (between.startswith('(') and between.endswith(')')):
                        # This is a braceless lambda
                        # Find the indent of the lambda line
                        lambda_indent = len(line) - len(line.lstrip())
                        
                        # Find the body lines (lines with indent > lambda_indent)
                        body_start = i + 1
                        body_end = body_start
                        
                        if body_start < len(lines):
                            first_body_line = lines[body_start]
                            first_body_indent = len(first_body_line) - len(first_body_line.lstrip())
                            
                            if first_body_indent > lambda_indent:
                                # There is a body - find its extent
                                body_end = body_start
                                while body_end < len(lines):
                                    body_line = lines[body_end]
                                    if body_line.strip() == '':
                                        body_end += 1
                                        continue
                                    body_line_indent = len(body_line) - len(body_line.lstrip())
                                    if body_line_indent <= lambda_indent:
                                        break
                                    body_end += 1
                                
                                if body_end > body_start:
                                    # Transform the lambda
                                    # 1. Replace trailing : with {
                                    new_lambda_line = stripped[:-1] + ' {'
                                    result.append(line[:lambda_indent] + new_lambda_line.lstrip())
                                    
                                    # 2. Process body lines (add semicolons if needed)
                                    for j in range(body_start, body_end):
                                        body_line = lines[j]
                                        body_stripped = body_line.rstrip()
                                        if body_stripped and not body_stripped.endswith((';', '{', '}', ':')):
                                            # Check if it's not a continuation
                                            if not body_stripped.startswith((',', ')', ']')):
                                                body_line = body_stripped + ';'
                                                body_indent = len(lines[j]) - len(lines[j].lstrip())
                                                result.append(' ' * body_indent + body_line.lstrip())
                                            else:
                                                result.append(body_line)
                                        else:
                                            result.append(body_line)
                                    
                                    # 3. Add closing brace at the lambda signature's indent level
                                    result.append(' ' * lambda_indent + '}')
                                    
                                    i = body_end
                                    continue
            
            result.append(line)
            i += 1
        
        return result
    
    def _handle_statement(self, ll: LogicalLine):
        """Handle a regular statement (add semicolon if needed)"""
        # Check for 'pass' statement - it's a no-op placeholder
        m = ll.meaningful
        if len(m) == 1 and m[0].kind == TokenKind.IDENTIFIER and m[0].spelling == 'pass':
            # Skip pass statements
            return
        
        # Check if inside enum (no semicolons needed)
        if self.block_type_stack and self.block_type_stack[-1] == BlockType.ENUM:
            self._emit_raw_lines(ll)
            return
        
        # Transform any inline braceless lambdas
        working_lines = self._transform_inline_braceless_lambdas(list(ll.raw_lines))
        
        # Check if needs semicolon
        if self._needs_semicolon(ll):
            # Add semicolon to the last line
            modified_lines = list(working_lines)
            if modified_lines:
                last_line_idx = len(modified_lines) - 1
                last_line = modified_lines[last_line_idx]
                last_physical_line = ll.start_line + last_line_idx
                
                # Find comment on the last line
                comment_tokens = [t for t in ll.tokens if t.kind == TokenKind.COMMENT and t.line == last_physical_line]
                if comment_tokens:
                    # Has comment - insert semicolon before it, preserving original spacing
                    comment_start = comment_tokens[0].column - 1
                    before_comment = last_line[:comment_start].rstrip()
                    # Preserve original whitespace between code and comment
                    code_end = len(last_line[:comment_start].rstrip())
                    original_spacing = last_line[code_end:comment_start]
                    comment_part = last_line[comment_start:]
                    modified_lines[last_line_idx] = before_comment + ';' + original_spacing + comment_part
                else:
                    # Preserve trailing whitespace after the semicolon
                    stripped_line = last_line.rstrip()
                    trailing_ws = last_line[len(stripped_line):] if len(last_line) > len(stripped_line) else ''
                    modified_lines[last_line_idx] = stripped_line + ';' + trailing_ws
            self._emit_raw_lines(ll, modified_lines)
        else:
            self._emit_raw_lines(ll, working_lines)
    
    def _needs_semicolon(self, ll: LogicalLine) -> bool:
        """Check if a statement needs a semicolon"""
        m = ll.meaningful
        if not m:
            return False
        
        last = m[-1]
        
        # Already has semicolon
        if last.spelling == ';':
            return False
        
        # Opening brace - no semicolon
        if last.spelling == '{':
            return False
        
        # Closing brace - check for initializer pattern
        if last.spelling == '}':
            # Check for = { ... } pattern (initializer)
            # Must have = directly followed by { (not separated by other things like )
            for i, t in enumerate(m):
                if t.spelling == '=' and i + 1 < len(m) and m[i + 1].spelling == '{':
                    return True
            # Lambda patterns that need semicolons
            if has_lambda_pattern(m):
                # Lambda with assignment (auto f = []() {...})
                has_equals = any(t.spelling == '=' for t in m)
                if has_equals:
                    return True
                # Lambda in return statement (return []() {...})
                first_token = m[0]
                if first_token.kind == TokenKind.KEYWORD and first_token.spelling == 'return':
                    return True
            return False
        
        # Preprocessor - no semicolon
        first = m[0]
        if first.spelling == '#':
            return False
        
        # Line starting with comma or closing paren is continuation - no semicolon
        if first.spelling in (',', ')', ']'):
            return False
        
        return True
    
    def _push_block(self, ll: LogicalLine, block_type: BlockType):
        """Push a new block onto the stack"""
        # Determine the indent of the block content by looking at next logical line
        # For now, just use current indent + 4 as placeholder
        # The actual content indent will be determined when we see the next line
        
        # Find the next non-blank logical line to get its indent
        ll_idx = self.logical_lines.index(ll)
        content_indent = ll.indent + 4  # Default
        
        for next_ll in self.logical_lines[ll_idx + 1:]:
            if not next_ll.is_blank_or_comment():
                if next_ll.indent > ll.indent:
                    content_indent = next_ll.indent
                break
        
        self.indent_stack.append(content_indent)
        self.block_type_stack.append(block_type)
        self.whitespace_stack.append(ll.leading_ws)
    
    def _output_closing_brace(self, block_type: BlockType, closing_ws: str = ""):
        """Output a closing brace with optional semicolon"""
        needs_semi = block_type in (BlockType.CLASS, BlockType.STRUCT, BlockType.ENUM, BlockType.UNION, BlockType.LAMBDA)
        
        closing = f"{closing_ws}}}"
        if needs_semi:
            closing += ';'
        
        self.output.append(closing)
    
    def _flush_blank_lines(self):
        """Output any pending blank lines"""
        if self.pending_blank_lines:
            # Extract raw lines from tuples (raw, indent, source_line)
            buffered = []
            for item in self.pending_blank_lines:
                if isinstance(item, tuple):
                    raw = item[0]
                    src_line = item[2] if len(item) >= 3 else 0
                    buffered.append((raw, src_line))
                else:
                    buffered.append((item, 0))
            self._emit_buffered_lines(buffered)
            self.pending_blank_lines = []
    
    def _emit_buffered_lines(self, buffered: List[Tuple[str, int]]):
        """Emit buffered lines (from pending_blank_lines). Can be overridden for line tracking.
        
        Args:
            buffered: List of (raw_line, source_line) tuples
        """
        for raw, src_line in buffered:
            self.output.append(raw)
    
    def _emit_raw_lines(self, ll: 'LogicalLine', lines: List[str] = None):
        """Emit raw lines from a logical line. Can be overridden for line tracking.
        
        Args:
            ll: The logical line (for source line info)
            lines: Lines to emit (defaults to ll.raw_lines)
        """
        if lines is None:
            lines = ll.raw_lines
        self.output.extend(lines)


# =============================================================================
# Compiler Wrapper Infrastructure
# =============================================================================


class TrackedOutputList(list):
    """A list that tracks source line mappings for each appended item"""
    
    def __init__(self, get_source_line_func):
        super().__init__()
        self._get_source_line = get_source_line_func
        self.source_lines: List[int] = []
    
    def append(self, item):
        super().append(item)
        self.source_lines.append(self._get_source_line())
    
    def extend(self, items):
        for item in items:
            self.append(item)
    
    def pop(self, index=-1):
        """Override pop to also remove the corresponding source line entry"""
        result = super().pop(index)
        self.source_lines.pop(index)
        return result


class LineMapper:
    """Provides source line lookup from tracked output"""
    
    def __init__(self, tracked_output: TrackedOutputList):
        self._tracked_output = tracked_output
    
    def get_source_line(self, output_line: int) -> int:
        """Get the source line for a given output line (1-based)"""
        idx = output_line - 1
        if 0 <= idx < len(self._tracked_output.source_lines):
            return self._tracked_output.source_lines[idx]
        return output_line


class MappingTokenCompiler(TokenCompiler):
    """Extended TokenCompiler that tracks line number mappings at the point of emission"""
    
    def __init__(self, lines: List[str]):
        super().__init__(lines)
        self._source_line_context = 1
        self.output = TrackedOutputList(lambda: self._source_line_context)
        self.line_mapper = LineMapper(self.output)
        # Store the current logical line for proper line tracking
        self._current_ll = None
    
    def _emit_raw_lines(self, ll: 'LogicalLine', lines: List[str] = None):
        """Override to emit raw lines with proper source line tracking.
        
        Each output line is tagged with its corresponding source line number,
        so multiline logical lines map correctly.
        
        Args:
            ll: The logical line (for source line info)
            lines: Lines to emit (defaults to ll.raw_lines)
        """
        if lines is None:
            lines = ll.raw_lines
        for i, line in enumerate(lines):
            self._source_line_context = ll.start_line + i
            self.output.append(line)
    
    def _emit_buffered_lines(self, buffered: List[Tuple[str, int]]):
        """Override to emit buffered lines with proper source line tracking.
        
        Each buffered line is tagged with its own source line, but the context
        is restored afterwards so that subsequent emissions use the correct line.
        
        Args:
            buffered: List of (raw_line, source_line) tuples
        """
        saved_context = self._source_line_context
        for raw, src_line in buffered:
            if src_line > 0:
                self._source_line_context = src_line
            self.output.append(raw)
        # Restore context so subsequent emissions use the current logical line's source line
        self._source_line_context = saved_context
    
    def compile(self) -> str:
        """Compile the braceless C++ to regular C++, tracking line mappings"""
        for ll in self.logical_lines:
            # Set context to the start line of this logical line
            self._source_line_context = ll.start_line
            self._current_ll = ll
            self._process_logical_line(ll)
        
        # Close any remaining blocks - use last line as context
        self._source_line_context = len(self.lines) if self.lines else 1
        saved_blank_lines = self.pending_blank_lines
        self.pending_blank_lines = []
        
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            block_type = self.block_type_stack.pop() if len(self.block_type_stack) > 1 else BlockType.NORMAL
            closing_ws = self.whitespace_stack.pop() if len(self.whitespace_stack) > 1 else ''
            self._output_closing_brace(block_type, closing_ws)
        
        # Output any remaining blank lines - need to handle tuples from pending_blank_lines
        for item in saved_blank_lines:
            if isinstance(item, tuple):
                raw, indent, src_line = item if len(item) == 3 else (item[0], item[1], self._source_line_context)
                self._source_line_context = src_line
                self.output.append(raw)
            else:
                self.output.append(item)
        
        return '\n'.join(self.output) + '\n'


class ErrorFormat(Enum):
    """Compiler error message formats"""
    MSVC = auto()      # file(line): error/warning
    GNU = auto()       # file:line:col: error/warning


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


def is_blcpp_file(filepath: str) -> bool:
    """Check if a file is a braceless C++ file"""
    return filepath.lower().endswith('.blcpp')


def is_blh_file(filepath: str) -> bool:
    """Check if a file is a braceless C++ header"""
    return filepath.lower().endswith('.blh')


# Pattern to match #include "*.blh" directives
BLH_INCLUDE_PATTERN = re.compile(r'^(\s*)#\s*include\s*"([^"]*\.blh)"', re.IGNORECASE)


def resolve_include(filename: str, search_dirs: List[str]) -> Optional[str]:
    """Find a header file in search directories.
    
    Args:
        filename: The filename from the #include directive
        search_dirs: List of directories to search
        
    Returns:
        Absolute path to the file if found, None otherwise
    """
    for dir_path in search_dirs:
        full_path = os.path.join(dir_path, filename)
        if os.path.exists(full_path):
            return os.path.abspath(full_path)
    return None


def expand_blh_includes(
    source_path: str,
    include_dirs: List[str] = None,
    included_files: Set[str] = None
) -> Tuple[List[str], Dict[int, Tuple[str, int]]]:
    """Expand all #include "*.blh" directives recursively.
    
    This function reads a source file and inlines any .blh headers it includes,
    tracking the original source location of each line.
    
    Args:
        source_path: Path to the source file to process
        include_dirs: Additional directories to search for headers
        included_files: Set of already-included files (for #pragma once handling)
        
    Returns:
        Tuple of:
        - lines: List of lines with .blh content inlined
        - line_map: Dict mapping output_line_num -> (original_file, original_line_num)
    """
    if included_files is None:
        included_files = set()
    
    source_path = os.path.abspath(source_path)
    source_dir = os.path.dirname(source_path)
    search_dirs = [source_dir] + (include_dirs or [])
    
    lines = []
    line_map = {}
    
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            source_lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"Cannot open source file: {source_path}")
    
    for src_line_num, line in enumerate(source_lines, 1):
        match = BLH_INCLUDE_PATTERN.match(line)
        
        if match:
            indent = match.group(1)
            blh_name = match.group(2)
            blh_path = resolve_include(blh_name, search_dirs)
            
            if blh_path is None:
                # Header not found - keep the include line as-is
                # The C++ compiler will report the error
                output_line = len(lines) + 1
                lines.append(line)
                line_map[output_line] = (source_path, src_line_num)
            elif blh_path in included_files:
                # Already included (handles #pragma once semantics)
                # Skip this include entirely
                pass
            else:
                # Expand the header
                included_files.add(blh_path)
                sub_lines, sub_map = expand_blh_includes(blh_path, include_dirs, included_files)
                
                # Add all lines from the included file
                base_output_line = len(lines)
                for i, sub_line in enumerate(sub_lines):
                    output_line = base_output_line + i + 1
                    lines.append(sub_line)
                    # Copy the source location from the sub-expansion
                    line_map[output_line] = sub_map[i + 1]
        else:
            # Regular line - add it with its source location
            output_line = len(lines) + 1
            lines.append(line)
            line_map[output_line] = (source_path, src_line_num)
    
    return lines, line_map


def extract_include_dirs(args: List[str]) -> List[str]:
    """Extract include directories from compiler arguments.
    
    Handles both -I dir and -Idir forms.
    """
    include_dirs = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '-I' and i + 1 < len(args):
            include_dirs.append(args[i + 1])
            i += 2
        elif arg.startswith('-I'):
            include_dirs.append(arg[2:])
            i += 1
        elif arg.startswith('/I'):  # MSVC style
            if len(arg) > 2:
                include_dirs.append(arg[2:])
            elif i + 1 < len(args):
                include_dirs.append(args[i + 1])
                i += 1
            i += 1
        else:
            i += 1
    return include_dirs


class SourceLocationMapper:
    """Maps transpiled line numbers back to original source file locations.
    
    This handles the case where .blh files have been expanded inline,
    so errors can be reported with the correct original file and line.
    """
    
    def __init__(self, blh_line_map: Dict[int, Tuple[str, int]], transpile_mapper: LineMapper):
        """
        Args:
            blh_line_map: Maps expanded_line -> (original_file, original_line)
            transpile_mapper: Maps transpiled_line -> expanded_line
        """
        self._blh_map = blh_line_map
        self._transpile_mapper = transpile_mapper
    
    def get_source_location(self, transpiled_line: int) -> Tuple[str, int]:
        """Get the original source file and line for a transpiled line number.
        
        Returns:
            Tuple of (original_file_path, original_line_number)
        """
        # First map transpiled line to expanded line
        expanded_line = self._transpile_mapper.get_source_line(transpiled_line)
        # Then map expanded line to original source location
        if expanded_line in self._blh_map:
            return self._blh_map[expanded_line]
        # Fallback: return unknown location
        return ("<unknown>", expanded_line)


def transpile_file(source_path: str, output_path: str, include_dirs: List[str] = None) -> SourceLocationMapper:
    """Transpile a braceless C++ file to regular C++.
    
    This function expands any #include "*.blh" directives, transpiles the
    combined braceless code to braced C++, and returns a mapper that can
    translate transpiled line numbers back to original source locations.
    
    Args:
        source_path: Path to the .blcpp source file
        output_path: Path where the transpiled .cpp will be written
        include_dirs: Additional directories to search for .blh headers
        
    Returns:
        SourceLocationMapper for mapping error line numbers back to original files
    """
    # Expand .blh includes recursively
    lines, blh_line_map = expand_blh_includes(source_path, include_dirs)
    
    # Transpile the expanded content using the token-based compiler with line tracking
    compiler = MappingTokenCompiler(lines)
    output = compiler.compile()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)
    
    # Return a mapper that chains: transpiled_line -> expanded_line -> (file, line)
    return SourceLocationMapper(blh_line_map, compiler.line_mapper)


def expand_response_file(response_file: str) -> List[str]:
    """Expand @response_file to its contents"""
    try:
        filepath = response_file[1:]
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        args = []
        current = []
        in_quotes = False
        for char in content:
            if char == '"':
                in_quotes = not in_quotes
            elif char in ' \t\n\r' and not in_quotes:
                if current:
                    args.append(''.join(current))
                    current = []
            else:
                current.append(char)
        if current:
            args.append(''.join(current))
        return args
    except Exception:
        return [response_file]


def parse_gnu_args(args: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """Parse GNU-style compiler arguments and identify source files."""
    source_files = {}
    expanded_args = []
    force_files = False
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg == '--':
            force_files = True
            expanded_args.append(arg)
            i += 1
            continue
        
        if force_files:
            if is_blcpp_file(arg):
                source_files[arg] = arg
            expanded_args.append(arg)
            i += 1
            continue
        
        if arg.startswith('@'):
            expanded = expand_response_file(arg)
            expanded_args.extend(expanded)
            _, nested_sources = parse_gnu_args(expanded)
            source_files.update(nested_sources)
            i += 1
            continue
        
        if arg == '-x' and i + 1 < len(args):
            expanded_args.append(arg)
            expanded_args.append(args[i + 1])
            i += 2
            continue
        
        if arg in ('-o', '-I', '-L', '-D', '-U', '-include', '-isystem', 
                   '-idirafter', '-iprefix', '-iwithprefix', '-MF', '-MT', '-MQ',
                   '-target', '--target', '-arch', '-framework', '-isysroot'):
            expanded_args.append(arg)
            if i + 1 < len(args):
                expanded_args.append(args[i + 1])
                i += 2
            else:
                i += 1
            continue
        
        if arg.startswith('-'):
            expanded_args.append(arg)
            i += 1
            continue
        
        if is_blcpp_file(arg):
            source_files[arg] = arg
        
        expanded_args.append(arg)
        i += 1
    
    return expanded_args, source_files


def parse_msvc_args(args: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """Parse MSVC-style compiler arguments (cl.exe, clang-cl) and identify source files."""
    source_files = {}
    expanded_args = []
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg.startswith('@'):
            expanded = expand_response_file(arg)
            expanded_args.extend(expanded)
            _, nested_sources = parse_msvc_args(expanded)
            source_files.update(nested_sources)
            i += 1
            continue
        
        # Handle /Tp and /Tc (force treat file as C++ or C)
        if arg.upper().startswith('/TP') or arg.upper().startswith('/TC'):
            if len(arg) > 3:
                filepath = arg[3:]
                if is_blcpp_file(filepath):
                    source_files[filepath] = filepath
            elif i + 1 < len(args):
                filepath = args[i + 1]
                if is_blcpp_file(filepath):
                    source_files[filepath] = filepath
            expanded_args.append(arg)
            i += 1
            continue
        
        if arg.startswith('/') or arg.startswith('-'):
            expanded_args.append(arg)
            i += 1
            continue
        
        if is_blcpp_file(arg):
            source_files[arg] = arg
        
        expanded_args.append(arg)
        i += 1
    
    return expanded_args, source_files


def _normalize_path(path: str) -> str:
    """Normalize a path for comparison"""
    return os.path.normcase(os.path.normpath(path))


def _paths_match(path1: str, path2: str) -> bool:
    """Check if two paths refer to the same file"""
    if _normalize_path(path1) == _normalize_path(path2):
        return True
    return os.path.basename(path1).lower() == os.path.basename(path2).lower()


def _build_basename_map(file_mappings: Dict[str, SourceLocationMapper]) -> Dict[str, str]:
    """Build a map of basenames to temp paths"""
    basename_to_temp = {}
    for temp_path in file_mappings:
        basename = os.path.basename(temp_path).lower()
        if basename.endswith('.cpp'):
            basename_to_temp[basename] = temp_path
    return basename_to_temp


def patch_compiler_output(
    output: str,
    file_mappings: Dict[str, SourceLocationMapper],
    error_format: ErrorFormat
) -> str:
    """Patch compiler output to map line numbers back to original source files.
    
    This handles errors from transpiled .cpp files, mapping them back to the
    original .blcpp or .blh source files and line numbers.
    
    Args:
        output: Compiler stdout or stderr
        file_mappings: Maps temp_cpp_path -> SourceLocationMapper
        error_format: MSVC or GNU error message format
        
    Returns:
        Patched output with corrected file paths and line numbers
    """
    basename_to_temp = _build_basename_map(file_mappings)
    lines = output.split('\n')
    patched_lines = []
    
    pattern = MSVC_ERROR_PATTERN if error_format == ErrorFormat.MSVC else GNU_ERROR_PATTERN
    
    for line in lines:
        match = pattern.match(line)
        if match:
            filepath = match.group(1)
            line_num = int(match.group(2))
            
            matched_temp_path = None
            for temp_path in file_mappings:
                if _paths_match(filepath, temp_path):
                    matched_temp_path = temp_path
                    break
            
            if not matched_temp_path:
                basename = os.path.basename(filepath).lower()
                if basename in basename_to_temp:
                    matched_temp_path = basename_to_temp[basename]
            
            if matched_temp_path:
                mapper = file_mappings[matched_temp_path]
                # Get the original source file and line
                original_path, source_line = mapper.get_source_location(line_num)
                
                if error_format == ErrorFormat.MSVC:
                    column_part = match.group(3) or ''
                    old_loc = f'({line_num}{column_part})'
                    new_loc = f'({source_line}{column_part})'
                    line = line.replace(filepath, original_path, 1)
                    line = line.replace(old_loc, new_loc, 1)
                else:
                    col_part = match.group(3)
                    if col_part:
                        old_loc = f'{filepath}:{line_num}:{col_part}:'
                        new_loc = f'{original_path}:{source_line}:{col_part}:'
                    else:
                        old_loc = f'{filepath}:{line_num}:'
                        new_loc = f'{original_path}:{source_line}:'
                    line = line.replace(old_loc, new_loc, 1)
        
        patched_lines.append(line)
    
    return '\n'.join(patched_lines)


def run_compiler_wrapper(
    wrapper_name: str,
    compiler_exe: str,
    args: List[str],
    parse_args_func,
    error_format: ErrorFormat,
    verbose: bool = False,
    keep_temp: bool = False
) -> int:
    """Generic compiler wrapper runner."""
    all_args, source_files = parse_args_func(args)
    blcpp_files = {path: path for path in source_files if is_blcpp_file(path)}
    
    if not blcpp_files:
        if verbose:
            print(f"[{wrapper_name}] No .blcpp files found, passing through to: {compiler_exe}", file=sys.stderr)
        cmd = subprocess.list2cmdline([compiler_exe] + args)
        result = subprocess.run(cmd, capture_output=False, shell=True)
        return result.returncode
    
    temp_dir = tempfile.mkdtemp(prefix=f'{wrapper_name}_')
    
    if verbose:
        print(f"[{wrapper_name}] Temp directory: {temp_dir}", file=sys.stderr)
    
    # Extract include directories for .blh resolution
    include_dirs = extract_include_dirs(all_args)
    
    try:
        file_mappings = {}
        new_args = list(all_args)
        
        for original_path in blcpp_files:
            base_name = os.path.basename(original_path)
            temp_name = os.path.splitext(base_name)[0] + '.cpp'
            temp_path = os.path.join(temp_dir, temp_name)
            
            try:
                if verbose:
                    print(f"[{wrapper_name}] Transpiling: {original_path} -> {temp_path}", file=sys.stderr)
                mapper = transpile_file(original_path, temp_path, include_dirs)
                file_mappings[temp_path] = mapper
                
                for i, arg in enumerate(new_args):
                    if arg == original_path:
                        new_args[i] = temp_path
            except FileNotFoundError as e:
                print(f"{wrapper_name}: error: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"{wrapper_name}: error transpiling {original_path}: {e}", file=sys.stderr)
                return 1
        
        if verbose:
            print(f"[{wrapper_name}] Running: {compiler_exe} {' '.join(new_args)}", file=sys.stderr)
        
        cmd = subprocess.list2cmdline([compiler_exe] + new_args)
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        
        if result.stdout:
            patched = patch_compiler_output(result.stdout, file_mappings, error_format)
            print(patched, end='')
        
        if result.stderr:
            patched = patch_compiler_output(result.stderr, file_mappings, error_format)
            print(patched, end='', file=sys.stderr)
        
        return result.returncode
        
    finally:
        if not keep_temp:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        elif verbose:
            print(f"[{wrapper_name}] Keeping temp directory: {temp_dir}", file=sys.stderr)


# Compiler configurations: (compiler_exe, error_format, parse_args_func)
COMPILERS = {
    'blcl':       ('cl.exe',    ErrorFormat.MSVC, parse_msvc_args),
    'blclang-cl': ('clang-cl',  ErrorFormat.MSVC, parse_msvc_args),
    'blgcc':      ('gcc',       ErrorFormat.GNU,  parse_gnu_args),
    'blg++':      ('g++',       ErrorFormat.GNU,  parse_gnu_args),
    'blclang':    ('clang',     ErrorFormat.GNU,  parse_gnu_args),
    'blclang++':  ('clang++',   ErrorFormat.GNU,  parse_gnu_args),
    'blemcc':     ('emcc',      ErrorFormat.GNU,  parse_gnu_args),
    'blem++':     ('em++',      ErrorFormat.GNU,  parse_gnu_args),
}


def wrapper_main(wrapper_name: str):
    """Main entry point for compiler wrappers."""
    if wrapper_name not in COMPILERS:
        print(f"Unknown wrapper: {wrapper_name}", file=sys.stderr)
        sys.exit(1)
    
    compiler_exe, error_format, parse_args_func = COMPILERS[wrapper_name]
    
    if len(sys.argv) < 2:
        print(f"{wrapper_name} - Braceless C++ wrapper for {compiler_exe}", file=sys.stderr)
        print(f"Usage: {wrapper_name} [{compiler_exe} options] <source files>", file=sys.stderr)
        print(f"       Accepts .blcpp files (braceless C++) in addition to regular C++ files", file=sys.stderr)
        print("", file=sys.stderr)
        print("Options:", file=sys.stderr)
        print("  --verbose    Show verbose output", file=sys.stderr)
        print("  --keep-temp  Don't delete temporary transpiled files", file=sys.stderr)
        sys.exit(1)
    
    args = sys.argv[1:]
    
    verbose = '--verbose' in args
    keep_temp = '--keep-temp' in args
    args = [arg for arg in args if arg not in ('--verbose', '--keep-temp')]
    
    exit_code = run_compiler_wrapper(
        wrapper_name=wrapper_name,
        compiler_exe=compiler_exe,
        args=args,
        parse_args_func=parse_args_func,
        error_format=error_format,
        verbose=verbose,
        keep_temp=keep_temp,
    )
    sys.exit(exit_code)


def main():
    # Check if invoked as a compiler wrapper
    if len(sys.argv) >= 3 and sys.argv[1] == '--wrapper':
        wrapper_name = sys.argv[2]
        sys.argv = [sys.argv[0]] + sys.argv[3:]  # Remove --wrapper and name from args
        wrapper_main(wrapper_name)
        return
    
    # Otherwise, run as transpiler
    if len(sys.argv) < 2:
        print("Usage: blcc <input.blcpp> [-I<include_dir>]...", file=sys.stderr)
        print("       blcc --wrapper <name> [compiler options] <source files>", file=sys.stderr)
        sys.exit(1)
    
    # Parse arguments
    filename = None
    include_dirs = []
    
    for arg in sys.argv[1:]:
        if arg.startswith('-I'):
            include_dirs.append(arg[2:])
        elif arg == '-I':
            continue  # Next arg will be the directory
        elif not filename:
            filename = arg
        elif sys.argv[sys.argv.index(arg) - 1] == '-I':
            include_dirs.append(arg)
    
    if not filename:
        print("Error: No input file specified", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Expand .blh includes and transpile
        lines, _ = expand_blh_includes(filename, include_dirs)
        compiler = TokenCompiler(lines)
        output = compiler.compile()
        print(output, end='')
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
