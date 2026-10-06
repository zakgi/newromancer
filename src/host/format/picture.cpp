#include "host/format/picture.hpp"

#include <algorithm>
#include <utility>

#include "host/format/big_endian.hpp"
#include "host/format/huffman.hpp"

namespace newromancer::host {

namespace {

constexpr std::uint8_t kCountMask = 0x7F;
constexpr std::uint8_t kLiteralFlag = 0x80;
constexpr std::size_t kIndexBits = 5;

// Color index of each chunky byte: its low five bits in reverse order.
consteval std::array<std::uint8_t, 256> BuildChunkyToIndex() {
  std::array<std::uint8_t, 256> table{};
  for (std::size_t value = 0; value < table.size(); ++value) {
    std::uint8_t index = 0;
    for (std::size_t bit = 0; bit < kIndexBits; ++bit) {
      index = static_cast<std::uint8_t>(index | (((value >> bit) & 1) << (kIndexBits - 1 - bit)));
    }
    table[value] = index;
  }
  return table;
}
constexpr std::array<std::uint8_t, 256> kChunkyToIndex = BuildChunkyToIndex();
static_assert(kChunkyToIndex[0x01] == 0x10 and kChunkyToIndex[0x17] == 0x1D and kChunkyToIndex[0xE1] == 0x10);

// Where record byte `position` lands: in sequence for rows, column by column for columns.
std::size_t TargetOf(std::size_t position, RunLength order, std::size_t row_bytes, std::size_t height) {
  std::size_t target = position;
  if (order == RunLength::Columns) {
    const std::size_t plane_size = row_bytes * height;
    const std::size_t plane = position / plane_size;
    const std::size_t column = (position % plane_size) / height;
    const std::size_t row = (position % plane_size) % height;
    target = (plane * plane_size) + (row * row_bytes) + column;
  }
  return target;
}

// Writes the `count` bytes of one record from `source`: the same byte repeated, or `count`
// literal bytes. Bytes past the end of the output only advance record_bytes.
void ExpandRecord(RunLengthResult& result, std::span<const std::uint8_t> source, bool literal, std::size_t count,
                  RunLength order, std::size_t row_bytes, std::size_t height) {
  for (std::size_t index = 0; index < count; ++index) {
    if (result.record_bytes < result.data.size()) {
      result.data[TargetOf(result.record_bytes, order, row_bytes, height)] = source[literal ? index : 0];
    }
    ++result.record_bytes;
  }
}

std::optional<DecodeError> CheckLayout(const PictureLayout& layout) {
  std::optional<DecodeError> error;
  if (layout.decode_type >= kDecodeTypes.size()) {
    error = DecodeError::UnknownDecodeType;
  } else if (layout.width == 0 or layout.height == 0 or
             (kDecodeTypes[layout.decode_type].planar and layout.width % 8 != 0)) {
    error = DecodeError::BadLayout;
  }
  return error;
}

// The 32 palette words into `palette`, then up to `decode_length` data bytes.
std::expected<std::vector<std::uint8_t>, DecodeError> ReadPaletteAndData(
    std::span<const std::uint8_t> stream, std::uint32_t decode_length,
    std::array<std::uint16_t, kPaletteColors>& palette) {
  std::expected<std::vector<std::uint8_t>, DecodeError> outcome;
  std::expected<HuffmanStream, DecodeError> huffman = HuffmanStream::Open(stream);
  const std::expected<std::vector<std::uint8_t>, DecodeError> colors =
      huffman ? huffman->Decode(kPaletteBytes) : std::unexpected{huffman.error()};
  if (not colors) {
    outcome = std::unexpected{colors.error()};
  } else if (colors->size() != kPaletteBytes) {
    outcome = std::unexpected{DecodeError::TruncatedPicture};
  } else {
    for (std::size_t index = 0; index < kPaletteColors; ++index) {
      palette[index] = ReadBigEndianU16(*colors, index * 2);
    }
    outcome = huffman->Decode(decode_length);
  }
  return outcome;
}

// The planes or chunky bytes of the picture, `size` bytes, before any line XOR.
std::expected<std::vector<std::uint8_t>, DecodeError> ExpandData(std::span<const std::uint8_t> data,
                                                                 RunLength run_length, std::size_t size,
                                                                 std::size_t row_bytes, std::size_t height) {
  std::expected<std::vector<std::uint8_t>, DecodeError> outcome;
  if (run_length == RunLength::None) {
    if (data.size() < size) {
      outcome = std::unexpected{DecodeError::TruncatedPicture};
    } else {
      outcome = std::vector<std::uint8_t>(data.begin(), data.begin() + static_cast<std::ptrdiff_t>(size));
    }
  } else if (std::expected<RunLengthResult, DecodeError> expanded =
                 DecodeRunLength(data, size, run_length, row_bytes, height)) {
    outcome = std::move(expanded->data);
  } else {
    outcome = std::unexpected{expanded.error()};
  }
  return outcome;
}

}  // namespace

std::expected<RunLengthResult, DecodeError> DecodeRunLength(std::span<const std::uint8_t> data, std::size_t size,
                                                            RunLength order, std::size_t row_bytes,
                                                            std::size_t height) {
  std::optional<DecodeError> error;
  const std::size_t plane_size = row_bytes * height;
  if (order == RunLength::None or plane_size == 0 or size % plane_size != 0) {
    error = DecodeError::BadLayout;
  }
  RunLengthResult result{.data = std::vector<std::uint8_t>(size, 0)};
  bool ended = false;
  while (not error and not ended and result.record_bytes < size) {
    const std::uint8_t control = result.consumed_bytes < data.size() ? data[result.consumed_bytes] : 0;
    const std::size_t count = control & kCountMask;
    const bool literal = (control & kLiteralFlag) != 0;
    const std::size_t source_start = result.consumed_bytes + 1;
    const std::size_t source_bytes = literal ? count : 1;
    ended = result.consumed_bytes < data.size() and count == 0;
    if (result.consumed_bytes >= data.size() or (not ended and source_start + source_bytes > data.size())) {
      error = DecodeError::TruncatedRecord;
    } else if (ended) {
      result.consumed_bytes = source_start;
    } else {
      ExpandRecord(result, data.subspan(source_start, source_bytes), literal, count, order, row_bytes, height);
      result.consumed_bytes = source_start + source_bytes;
    }
  }
  std::expected<RunLengthResult, DecodeError> outcome;
  if (error) {
    outcome = std::unexpected{*error};
  } else {
    outcome = std::move(result);
  }
  return outcome;
}

void XorAdjacentLines(std::span<std::uint8_t> planes, std::size_t row_bytes, std::size_t height) {
  const std::size_t plane_size = row_bytes * height;
  for (std::size_t plane_start = 0; plane_start + plane_size <= planes.size(); plane_start += plane_size) {
    for (std::size_t row = 1; row < height; ++row) {
      const std::size_t start = plane_start + (row * row_bytes);
      for (std::size_t column = 0; column < row_bytes; ++column) {
        planes[start + column] ^= planes[start + column - row_bytes];
      }
    }
  }
}

std::vector<std::uint8_t> PlanarToPixels(std::span<const std::uint8_t> planes, std::size_t row_bytes,
                                         std::size_t height) {
  const std::size_t plane_size = row_bytes * height;
  std::vector<std::uint8_t> pixels(plane_size * 8, 0);
  for (std::size_t plane = 0; plane < kPlaneCount; ++plane) {
    for (std::size_t offset = 0; offset < plane_size; ++offset) {
      const std::uint8_t bits = planes[(plane * plane_size) + offset];
      for (std::size_t bit = 0; bit < 8; ++bit) {
        if ((bits & (0x80U >> bit)) != 0) {
          pixels[(offset * 8) + bit] |= static_cast<std::uint8_t>(1U << plane);
        }
      }
    }
  }
  return pixels;
}

std::vector<std::uint8_t> ChunkyToPixels(std::span<const std::uint8_t> bytes) {
  std::vector<std::uint8_t> pixels(bytes.size());
  std::ranges::transform(bytes, pixels.begin(), [](std::uint8_t value) { return kChunkyToIndex[value]; });
  return pixels;
}

std::expected<Picture, DecodeError> DecodePicture(std::span<const std::uint8_t> stream, const PictureLayout& layout) {
  Picture picture{.width = layout.width, .height = layout.height, .pixels = {}, .palette = {}};
  std::optional<DecodeError> error = CheckLayout(layout);
  const DecodeType type = error ? DecodeType{} : kDecodeTypes[layout.decode_type];
  const std::size_t row_bytes = type.planar ? layout.width / 8U : layout.width;
  const std::size_t size = row_bytes * layout.height * (type.planar ? kPlaneCount : 1);
  std::expected<std::vector<std::uint8_t>, DecodeError> data = std::unexpected{DecodeError::BadLayout};
  if (not error) {
    data = ReadPaletteAndData(stream, layout.decode_length, picture.palette);
  }
  std::expected<std::vector<std::uint8_t>, DecodeError> planes = std::unexpected{DecodeError::BadLayout};
  if (not error and data) {
    planes = ExpandData(*data, type.run_length, size, row_bytes, layout.height);
  }
  if (not error and not data) {
    error = data.error();
  } else if (not error and not planes) {
    error = planes.error();
  } else if (not error) {
    if (type.xor_lines) {
      XorAdjacentLines(*planes, row_bytes, layout.height);
    }
    picture.pixels = type.planar ? PlanarToPixels(*planes, row_bytes, layout.height) : ChunkyToPixels(*planes);
  }
  std::expected<Picture, DecodeError> outcome;
  if (error) {
    outcome = std::unexpected{*error};
  } else {
    outcome = std::move(picture);
  }
  return outcome;
}

}  // namespace newromancer::host
