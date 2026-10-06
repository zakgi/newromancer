#include "host/format/offset_table.hpp"

#include <cstddef>
#include <optional>
#include <utility>

#include "host/format/big_endian.hpp"

namespace newromancer::host {

std::expected<std::vector<std::span<const std::uint8_t>>, DecodeError> ReadEntries(std::span<const std::uint8_t> data) {
  std::optional<DecodeError> error;
  std::vector<std::size_t> offsets;
  std::size_t position = 0;
  bool done = false;
  while (not done and not error) {
    if (position + sizeof(std::uint32_t) > data.size()) {
      error = DecodeError::TruncatedTable;
    } else {
      const std::uint32_t offset = ReadBigEndianU32(data, position);
      position += sizeof(std::uint32_t);
      done = offset == 0;
      if (not done) {
        offsets.push_back(offset);
      }
    }
  }
  for (const std::size_t offset : offsets) {
    if (not error and (offset < position or offset >= data.size())) {
      error = DecodeError::OffsetOutOfRange;
    }
  }
  std::vector<std::span<const std::uint8_t>> entries;
  for (std::size_t index = 0; index < offsets.size() and not error; ++index) {
    const std::size_t end = index + 1 < offsets.size() ? offsets[index + 1] : data.size();
    if (end < offsets[index]) {
      error = DecodeError::OffsetOutOfRange;
    } else {
      entries.push_back(data.subspan(offsets[index], end - offsets[index]));
    }
  }
  std::expected<std::vector<std::span<const std::uint8_t>>, DecodeError> outcome;
  if (error) {
    outcome = std::unexpected{*error};
  } else {
    outcome = std::move(entries);
  }
  return outcome;
}

}  // namespace newromancer::host
