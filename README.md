# Braceless C++

Braceless C++ is a dialect of C++ that uses Python-style indentation instead of braces.

It compiles to standard C++ and comes with wrappers for Clang, GCC, and MSVC. Since you can mix indentation and braces freely in the same file, you can adopt the braceless style one function at a time. Trailing semicolons and parentheses in control structures are optional.

## Usage

```bash
braceless clang++ main.blcpp -o main
```

```bash
braceless g++ main.blcpp -o main
```

```bash
braceless cl.exe main.blcpp /Fe:main.exe
```

## Example

<table>
<tr>
<th>Braceless C++</th>
<th>Transpiled C++</th>
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
