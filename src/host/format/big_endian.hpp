#pragma once

#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>

namespace newromancer::host {

// Big-endian field readers for the original 68000 files. The caller has checked that `offset`
// plus the field width lies inside `bytes`.

inline std::uint16_t ReadBigEndianU16(std::span<const std::uint8_t> bytes, std::size_t offset) {
  std::uint16_t value = 0;
  std::memcpy(&value, bytes.subspan(offset, sizeof(value)).data(), sizeof(value));
  if constexpr (std::endian::native == std::endian::little) {
    value = std::byteswap(value);
  }
  return value;
}

inline std::uint32_t ReadBigEndianU32(std::span<const std::uint8_t> bytes, std::size_t offset) {
  std::uint32_t value = 0;
  std::memcpy(&value, bytes.subspan(offset, sizeof(value)).data(), sizeof(value));
  if constexpr (std::endian::native == std::endian::little) {
    value = std::byteswap(value);
  }
  return value;
}

}  // namespace newromancer::host
