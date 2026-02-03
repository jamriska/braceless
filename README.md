# Braceless C++

Braceless C++ is a dialect of C++ that uses indentation instead of braces and compiles to regular C++. 

It comes with wrappers for Clang, GCC, MSVC, and Emscripten: ``blclang``, ``blgcc``, ``blcl``, ``blemcc``.

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
