# Building

The executable currently opens an empty window; the port fills it step by step
([port-plan.md](port-plan.md)).

Use CMake 3.28 or newer, Ninja and a C++23 compiler. The first configure
downloads the pinned ADFlib, SFML, args, spdlog and GoogleTest sources into
`.cache/fetchcontent/`, shared by every build directory.

```sh
cmake --preset host
cmake --build --preset host
```

| Preset | Build type | Directory |
| --- | --- | --- |
| `host` | Debug | `build/` |
| `host-release` | Release | `build-release/` |

Run `build/newromancer`. `--scaling 3` (the default) selects a 960-by-600
window; scales from 1 through 8 are supported, and `--help` lists the options.
Close the window or press Escape to exit.

## Tests

`NEWROMANCER_BUILD_TESTS` (default `ON`) builds `newromancer_tests`:

```sh
cmake --build --preset host
ctest --preset host
```

Tests that need the game's files read the original disk image from
`NEWROMANCER_ADF` (default `assets/Neuromancer.adf`) and skip when it is absent.
They check the decoders against digests computed with the Python tools
([extractor.md](extractor.md)). To use an image elsewhere:

```sh
cmake --preset host -DNEWROMANCER_ADF=/path/to/Neuromancer.adf
```

## Code intelligence

Every configure points `compile_commands.json` at the repository root to its
build directory's database, so clangd follows the last-configured build. A
regular file at that path is left in place.
