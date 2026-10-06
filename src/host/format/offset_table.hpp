#pragma once

#include <cstdint>
#include <expected>
#include <span>
#include <vector>

#include "host/format/decode_error.hpp"

namespace newromancer::host {

// The entries the offset table at the start of a big* file delimits (docs/picture-formats.md,
// "Offset table"): each runs from its offset to the next one, the last to the end of `data`.
// The spans view `data`.
[[nodiscard]] std::expected<std::vector<std::span<const std::uint8_t>>, DecodeError> ReadEntries(
    std::span<const std::uint8_t> data);

}  // namespace newromancer::host
