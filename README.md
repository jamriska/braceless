# Braceless C++

Braceless C++ lets you write C++ using indentation instead of braces. It compiles to standard C++ and works with Clang, GCC, MSVC, and Emscripten. It is backwards compatible with regular C++ and you can freely mix indentation and braces in the same source file. Trailing semicolons and parentheses in control structures are optional.

<table>
<tr>
<th>Braceless C++</th>
<th>Compiled C++</th>
</tr>
<tr>
<td valign="top">

```nim
int clamp(int x, int lo, int hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x

int main():
    int sum = 0
    for int i = 0; i < 10; i++:
        if i % 2 == 0:
            sum += clamp(i, 2, 8)
    return sum
```

</td>
<td valign="top">

```cpp
int clamp(int x, int lo, int hi) {
    if (x < lo) {
        return lo;
    }
    if (x > hi) {
        return hi;
    }
    return x;
}

int main() {
    int sum = 0;
    for (int i = 0; i < 10; i++) {
        if (i % 2 == 0) {
            sum += clamp(i, 2, 8);
        }
    }
    return sum;
}
```
</td>
</tr>
</table>

## Usage

Use the wrapper that corresponds to your compiler:

```bash
# Clang
blclang++ main.blcpp -o main

# GCC
blg++ main.blcpp -o main

# MSVC
blcl main.blcpp /Fe:main.exe
```
