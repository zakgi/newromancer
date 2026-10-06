#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <utility>

namespace newromancer::host {

// Failure reasons shared by the decoders of the original files. See docs/picture-formats.md.
// Values index kDecodeErrorNames.
enum class DecodeError : std::uint8_t {
  TruncatedTable = 0,     // offset table: no terminating zero entry
  OffsetOutOfRange = 1,   // offset table: an entry points outside the data
  TruncatedHeader = 2,    // Huffman: the stream is shorter than its header
  TreeTooLarge = 3,       // Huffman: more nodes than a byte alphabet needs
  TruncatedStream = 4,    // Huffman: the bits ran out before the requested bytes
  UnknownDecodeType = 5,  // picture: a decode type beyond the known nine
  BadLayout = 6,          // picture: a size that cannot hold whole rows and planes
  TruncatedRecord = 7,    // run-length: a record runs past the end of the data
  TruncatedPicture = 8,   // picture: fewer palette or pixel bytes than the layout needs
};

inline constexpr auto kDecodeErrorNames = std::to_array<std::pair<DecodeError, std::string_view>>({
    {DecodeError::TruncatedTable, "offset table without terminating zero"},
    {DecodeError::OffsetOutOfRange, "offset outside the data"},
    {DecodeError::TruncatedHeader, "truncated stream header"},
    {DecodeError::TreeTooLarge, "code tree too large"},
    {DecodeError::TruncatedStream, "truncated bit stream"},
    {DecodeError::UnknownDecodeType, "unknown decode type"},
    {DecodeError::BadLayout, "invalid picture layout"},
    {DecodeError::TruncatedRecord, "truncated run-length record"},
    {DecodeError::TruncatedPicture, "truncated picture data"},
});

consteval bool DecodeErrorNamesAreInOrder() {
  bool in_order = true;
  for (std::size_t index = 0; index < kDecodeErrorNames.size(); ++index) {
    in_order = in_order and std::to_underlying(kDecodeErrorNames[index].first) == index;
  }
  return in_order;
}
static_assert(DecodeErrorNamesAreInOrder(), "kDecodeErrorNames must be indexed by DecodeError value");

[[nodiscard]] constexpr std::string_view ToString(DecodeError error) {
  std::string_view text{"unknown decode error"};
  const std::size_t index = std::to_underlying(error);
  if (index < kDecodeErrorNames.size()) {
    text = kDecodeErrorNames[index].second;
  }
  return text;
}

}  // namespace newromancer::host
