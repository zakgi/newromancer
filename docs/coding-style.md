# Newromancer coding style

Newromancer is a native, multiplatform C++23 port of the Amiga version of
Neuromancer. Readable code, documented behavior, and preservation of the
original formats are project goals. Python tools extract and explain resources
before those resources are used by the port.

This document is self-contained. Update it when an agreed convention changes.

## Formatting and source organization

- Use C++23. Headers use `#pragma once` and include their own dependencies.
- Use the `newromancer` namespace, with descriptive nested namespaces where
  useful.
- [`.clang-format`](../.clang-format) and [`.clangd`](../.clangd) govern
  formatting and diagnostics. Discuss changes to either configuration first.
- The current formatter uses a Google-derived style, two-space indentation,
  a 120-column limit, unindented namespace bodies, and pointer-left spelling
  such as `Widget*`.
- Run `clang-format` on changed C++ files before considering an edit complete.
  Keep unrelated formatting changes out of the edit.
- Use ASCII in source files, comments, identifiers, and technical notation.
- Keep files focused on a format or subsystem. Avoid generic utility layers
  until there is a concrete shared use.

## Names

| Item | Convention | Example |
| --- | --- | --- |
| Types and member/free functions | `PascalCase` | `ArchiveEntry`, `ReadEntry` |
| Variables, parameters, fields, files, namespaces | `snake_case` | `file_offset`, `archive_reader.cpp` |
| Compile-time constants | `kCamelCase` | `kArchiveEntrySize` |
| Preprocessor macros | `UPPER_SNAKE_CASE` | Use only when required |

Use descriptive names of at least three characters for variables, parameters,
and fields. Prefer `index`, `offset`, or `count` to single-letter counters.
Type names and enumerators are exempt from the length rule.

Include units when the type does not make them clear: `elapsed_us`,
`sample_rate_hz`, `size_bytes`. Distinguish file offsets, resource offsets,
hunk offsets, and runtime addresses.

Name synchronous operations with direct verbs such as `Load`, `Decode`,
`Advance`, or `Render`. Reserve `On...` for actual callbacks; framework-defined
callback names retain their required spelling.

Parameter names appear in declarations and match their definitions. Mark
unused parameters `[[maybe_unused]]`; do not replace their names with comments.

## Values, ownership, and containers

Prefer values and references. Use pointers only where necessary, such as an
external API boundary or a representation that requires indirection. Make
ownership and lifetime explicit, and keep pointer manipulation contained.
Do not use a null pointer merely as a substitute for an optional result.

- Use `std::array` for fixed storage and `std::span` for buffer views.
  Do not expose raw pointer-plus-length interfaces.
- Core, target and board code use no dynamic allocation: no `new`, no
  `malloc`, and no allocating standard library types such as `std::vector`,
  `std::string`, `std::function` or `std::map`. Use owned fixed-size arrays
  or caller-provided buffers with explicit target capacities. This does not
  require global mutable objects. Document capacity and overflow handling for
  bounded containers. Dynamic allocation is limited to host code, tools and
  tests.
- Use `std::to_array` when a literal determines the length. Use
  `std::array<T, N>` when a named bound is part of the format or contract.
- Do not use C arrays for storage. A reference to a C array is acceptable
  when required to deduce a string literal's size; convert to a standard view
  at the boundary. Required external signatures are also boundary exceptions.
- Prefer `std::string_view` for borrowed text. Document the backing lifetime
  of views and references.
- Accept spans or suitably constrained ranges where an operation should
  work with different contiguous containers.
- Use RAII for resources. Avoid manual `new`/`delete`, `malloc`/`free`, C-style
  casts, C string manipulation, and macros standing in for typed operations.

`std::span` and `std::array` do not automatically validate every index in
C++23. Check input-derived indices and ranges explicitly. A view must never
outlive its backing storage.

## Types and binary data

- Use fixed-width integer types for file fields, registers, and arithmetic
  whose width affects behavior. Use `std::size_t` for host buffer sizes.
- Use `enum class` with an explicit underlying type.
- Prefer braced initialization and initialize state deliberately.
- Prefer `constexpr` and `consteval` for tables and compile-time work.
  Tables should not require dynamic initialization or allocation at startup.
- Decode file bytes into typed records once, in the host loader, which owns
  the layout knowledge: offsets, field widths, parallel arrays. Present the
  result the way a modern engine consumes it, as arrays of structs, spans and
  native integer types. Do not carry storage layouts, original buffer sizes or
  the original program's memory limits into engine-facing types.
- Validate lengths, counts, offsets, and arithmetic before accessing data.
  Unknown fields remain explicitly unknown until supported by evidence.

Preserve original behavior where it depends on wrapping, sign extension or
discrete transitions. Express required operations deliberately with defined
C++ semantics; do not rely on signed overflow or reproduce decompiler casts
mechanically. Document the instruction or routine establishing the behavior in
the format or subsystem document.

Rendering must support desktop and microcontroller targets through a
platform-independent scene and draw contract. Keep GPU APIs, display
drivers, pixel storage and transfer details in backends/adapters. Prefer
concepts and compile-time backend selection. Support bounded batches and
explicit working-memory budgets, with no per-frame heap allocation in the
render loop. Do not require a GPU, full-frame depth storage, filesystem or
double precision throughout the shared renderer. Preserve the agreed
projection and material semantics across GPU and software implementations.

## Errors and core boundaries

Shared/core code uses neither exceptions nor RTTI. This includes headers
included by the core: no `throw`, `try`/`catch`, `dynamic_cast`, or `typeid`.

Use `std::optional<T>` when absence is the only failure information needed.
Use `std::expected<T, Error>` when callers need to distinguish errors. Avoid
magic sentinel results and error output parameters. Mark results
`[[nodiscard]]` when ignoring them would lose necessary validation.

Host-only code may catch exceptions from dependencies such as `args` or from
system integration. Translate failures at that boundary; exceptions must not
escape into the core. Scope compiler settings accordingly instead of
disabling exceptions globally for third-party libraries that require them.

The core models the game and operates on explicit state and resource views.
SFML windowing, input devices, audio transport, filesystem access, CLI parsing,
and host diagnostics belong at the platform boundary. Use `std::filesystem`
and C++ streams for host file handling; choose error-code overloads where
non-throwing behavior is required.

## State and interfaces

Keep state, configuration, and resources inside the objects that own them.
Pass dependencies explicitly. Avoid ambient globals, file-static singletons,
and static class state. Per-template `static constexpr` constants are an
exception when they serve a compile-time purpose.

Use `const` honestly. Do not use `mutable` to hide state changes in a query.
Discuss a necessary memoization exception before introducing it.

Prefer templates and concepts to inheritance-based interfaces when the
implementation is selected at compile time. Do not introduce pure virtual
interfaces where a concept expresses the contract. Virtual functions are
acceptable where required by a framework or where there is a clear
devirtualization path. Platform variation should not force runtime dispatch
through otherwise portable engine code.

Lambdas are for small operations passed directly to algorithms or callbacks.
Use named free or member functions for reusable helpers. Avoid chains of
capturing lambdas that conceal control flow or object state.

## Control flow and performance

- Brace every `if`, `else`, `for`, `while`, and `do` body.
- Use `and`, `or`, and `not` for boolean logic. Ordinary bitwise and comparison
  operators keep their punctuation spelling.
- Prefer a single return at the end of a function. An entry guard is
  acceptable when it substantially reduces nesting. In a `switch`, prefer
  assigning a result and breaking, then returning after the switch.
- Prefer standard algorithms when they communicate the operation clearly.
  An explicit loop is appropriate when it makes a binary format or algorithm
  easier to understand.

Correctness and clear ownership come before speculative optimization. Keep
necessary low-level operations in small named helpers with documented
preconditions.

For real-time audio paths, preallocate storage and avoid allocation, locks,
file I/O, and logging in the processing loop or callback. Prefer `float` for
audio computation. These constraints concern time-critical paths; they are
not a blanket ban on dynamic containers in host loading and tooling code.

## Python extraction tools

Python scripts are readable reference implementations as well as utilities.
Use Python conventions: `snake_case` functions and variables, `PascalCase`
types, and `UPPER_SNAKE_CASE` module constants.

- Keep decoding functions separate from command-line parsing and file I/O.
- Use `argparse`, `pathlib`, and explicit-endian `struct` formats where they
  fit. Third-party Python libraries and tools are welcome when they improve
  readability, correctness, or maintainability. There is no standard-library-only
  requirement; avoid reimplementing established functionality just to eliminate
  a dependency. Declare dependencies and document installation and usage.
- Use descriptive names, type hints, and small functions. Model entities
  explicitly with dataclasses; avoid unnecessary class hierarchies.
- Put usage and format assumptions in module docstrings; evidence references
  belong in the documents.
- Validate truncated input, out-of-range offsets, impossible counts, and
  decompression termination. Report errors with the file and relevant offset.
- Preserve unknown bytes. Do not silently trim, pad, or repair data unless
  the format requires it and the behavior is documented.
- Leave source assets unchanged. Keep extracted resource bytes and converted
  previews distinguishable and write them to an explicit output directory.
- Build filesystem paths from `pathlib.Path` components; do not concatenate
  platform-specific separators. Use `PurePosixPath` for portable manifest
  paths, and convert them to native `Path` objects for filesystem access.
- Use PyPNG (`import png`) for PNG encoding rather than maintaining a custom
  PNG container writer. Preserve palette indices and supplied palette entries.
- Produce deterministic manifests with resource names or hashes, source
  files, offsets, stored/decoded sizes, and content digests as appropriate.
  Record transformations and unresolved filename mappings.

Python may use exceptions for parse and I/O failures. The no-exceptions rule
applies to the C++ core.

### Type annotations

Fully annotate Python code: function and method parameters, return values,
dataclass fields, instance attributes, local variables, and module/class
constants. Include `-> None` for operations that return no value. Ordinary
`self` and `cls` parameters rely on their enclosing class rather than a
redundant annotation.

Use precise container element types, tuple shapes, and unions, such as
`list[ArchiveEntry]`, `tuple[Palette, bytes]`, and `Palette | None`. Mark
class-level constants with `ClassVar[...]` so dataclasses do not treat them
as instance fields. Avoid bare containers and `Any` where the actual type
can be expressed. Factories and properties also declare their return types.

### Entities and object construction

Follow this construction pattern:

- Represent records, resources, palettes, and other domain entities with
  `@dataclass` and typed fields, rather than anonymous tuples or dictionaries
  passed throughout the program.
- Use meaningful field defaults where an empty or default state is valid.
  Use `field(default_factory=...)` for mutable collections and nested objects
  that each instance must own independently.
- Keep the generated dataclass constructor for assigning fields. Put binary
  parsing in named `@staticmethod` factories such as `from_data`,
  `from_packed_data`, or `from_chunk`, with an explicit return annotation.
  Call them as `ArchiveEntry.from_data(data)`.
- Inside factories, decode and validate the input, then construct the entity
  using named arguments, such as `Palette(colors=colors)`. Direct construction
  with `Record(*struct.unpack(...))` is appropriate for a simple record whose
  declared field order exactly matches the validated binary layout.
- For composite formats, a factory may construct a valid empty object,
  populate its children, and return the completed object. Keep file I/O out
  of constructors and binary parsing factories.
- Expose derived views and simple computed values through descriptive
  properties, such as a palette's alternative representations.

### Code generation

Generate code from readable triple-quoted string templates. Collect template
arguments in a dedicated proxy class (a dataclass is suitable), pass its
instance to `.format()`, and access its attributes through named placeholders:
`template.format(args=proxy)` with fields such as `{args.name}` and
`{args.size}`.

Keep value preparation and formatting helpers in the proxy, so the template
closely resembles the generated code. Escape literal braces in the template
as `{{` and `}}`. Use this pattern instead of assembling source through chains
of concatenations, f-strings, or line-by-line writes.

## Preservation documentation

Document each format and subsystem as it becomes understood. Write for a
reader who has not followed the investigation.

Format documents include field offsets, widths, byte order, signedness,
counts, compression rules, examples, validation results, and unknowns.
Subsystem documents explain purpose, state, call relationships, algorithms,
units, timing, and any intentional differences in the native port.

Distinguish evidence explicitly:

- **Observed:** established from binary data, disassembly, or a runtime trace.
- **Inferred:** an interpretation supported by evidence but not yet proven.
- **Unknown:** unresolved meaning or behavior.

Identify the executable or asset version, preferably by digest. Give addresses
in the executable as hunk number plus offset. State whether any other address
is a file offset or a runtime address, and document the conversion where
needed.

The repository ships no original game material: no disk images, extracted
files, executables, disassembly listings or text dumps. The host reads the
original disk image at runtime, identified by digest; tests that need it skip
when it is absent.

Cite original routines and data as behavioral evidence. Credit external
research and implementations, including their revision when relevant, while
distinguishing their claims from findings verified in our copy. Preserve
applicable attribution and license notices for reused code.

Code comments and docstrings explain present behavior and non-obvious reasons
concisely, without referring to the original code. Keep evidence,
investigation history and design decisions in Markdown. Labels and addresses
from analysis tools stay out of the repository. The documents link code and
extractor where they describe the same resource or algorithm.

## Working on changes

Discuss architecture before implementation and ask for permission before
writing or modifying code. A specific user instruction to implement a change
authorizes that change; keep the edit within that scope. Make small, reviewable
changes and update the relevant documentation alongside them.

Validate changes against the original assets and behavior. Use focused tests
for meaningful cases such as decompression boundaries, malformed inputs,
arithmetic edge cases, and behavioral regressions. Record what was checked
and what remains unverified. Keep the Python reference tools, C++ port and
documentation consistent as understanding improves.
