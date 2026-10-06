#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <optional>
#include <span>
#include <vector>

#include "host/format/decode_error.hpp"

namespace newromancer::host {

// Static pictures: room backgrounds (bigpic0158), game graphics (bigpic2) and AI faces
// (bigAIpic). See docs/picture-formats.md.

enum class RunLength : std::uint8_t { None, Rows, Columns };

// How a picture's data becomes pixels; the files do not store it.
struct DecodeType {
  RunLength run_length;
  bool xor_lines;
  bool planar;
};

inline constexpr auto kDecodeTypes = std::to_array<DecodeType>({
    {.run_length = RunLength::None, .xor_lines = true, .planar = true},
    {.run_length = RunLength::Rows, .xor_lines = true, .planar = true},
    {.run_length = RunLength::Columns, .xor_lines = true, .planar = true},
    {.run_length = RunLength::Columns, .xor_lines = false, .planar = true},
    {.run_length = RunLength::None, .xor_lines = true, .planar = false},
    {.run_length = RunLength::Rows, .xor_lines = true, .planar = false},
    {.run_length = RunLength::Columns, .xor_lines = true, .planar = false},
    {.run_length = RunLength::Rows, .xor_lines = false, .planar = false},
    {.run_length = RunLength::Columns, .xor_lines = false, .planar = false},
});
static_assert(kDecodeTypes.size() == 9);

inline constexpr std::size_t kPlaneCount = 5;
inline constexpr std::size_t kPaletteColors = 32;
inline constexpr std::size_t kPaletteBytes = kPaletteColors * 2;

// Picture size in pixels, decode type, and the number of data bytes taken from the stream.
struct PictureLayout {
  std::uint16_t width;
  std::uint16_t height;
  std::uint8_t decode_type;
  std::uint32_t decode_length;
};

inline constexpr std::uint32_t kFullDecodeLength = 64000;

inline constexpr std::size_t kRoomCount = 58;
inline constexpr std::uint16_t kRoomWidth = 304;
inline constexpr std::uint16_t kRoomHeight = 112;

inline constexpr std::optional<std::uint8_t> kNoPicture{};

// Decode type of each room's background, rooms 1 to 58; kNoPicture for rooms without one.
inline constexpr auto kRoomPictureTypes = std::to_array<std::optional<std::uint8_t>>(
    {5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 3, 3,          5, 3, 2, 2, 5,          5, 5, 5, 4, 2, 5, 3, 5, kNoPicture, 5,
     5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, kNoPicture, 1, 5, 5, 5, kNoPicture, 5, 4, 5, 7, 5, 5, 5, 5, 5,          5});
static_assert(kRoomPictureTypes.size() == kRoomCount);

consteval std::size_t CountRoomPictures() {
  std::size_t count = 0;
  for (const std::optional<std::uint8_t>& type : kRoomPictureTypes) {
    if (type) {
      ++count;
    }
  }
  return count;
}
inline constexpr std::size_t kRoomPictureCount = CountRoomPictures();
static_assert(kRoomPictureCount == 55);

struct RoomPicture {
  std::uint8_t room;
  PictureLayout layout;
};

// The backgrounds in bigpic0158, in file order: rooms with a picture, in room order.
consteval std::array<RoomPicture, kRoomPictureCount> BuildRoomPictures() {
  std::array<RoomPicture, kRoomPictureCount> pictures{};
  std::size_t count = 0;
  for (std::size_t index = 0; index < kRoomPictureTypes.size(); ++index) {
    if (kRoomPictureTypes[index]) {
      pictures[count] = RoomPicture{.room = static_cast<std::uint8_t>(index + 1),
                                    .layout = PictureLayout{.width = kRoomWidth,
                                                            .height = kRoomHeight,
                                                            .decode_type = *kRoomPictureTypes[index],
                                                            .decode_length = kFullDecodeLength}};
      ++count;
    }
  }
  return pictures;
}
inline constexpr std::array<RoomPicture, kRoomPictureCount> kRoomPictures = BuildRoomPictures();
static_assert(kRoomPictures.front().room == 1 and kRoomPictures.back().room == kRoomCount);

// Game graphics in bigpic2, numbered from 1 in file order.
inline constexpr auto kGameGraphics = std::to_array<PictureLayout>({
    // 1: splash screen
    {.width = 320, .height = 200, .decode_type = 2, .decode_length = kFullDecodeLength},
    // 2: player walking left and right
    {.width = 288, .height = 130, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 3: player walking up and down
    {.width = 288, .height = 130, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 4: walking up, turning head
    {.width = 160, .height = 130, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 5: walking down, turning head
    {.width = 160, .height = 130, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 6: walking right, turning head
    {.width = 160, .height = 130, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 7: walking left, turning head
    {.width = 160, .height = 130, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 8: turning by 45 degrees
    {.width = 256, .height = 65, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 9: dashboard and scene frame
    {.width = 320, .height = 200, .decode_type = 5, .decode_length = kFullDecodeLength},
    // 10: thought and dialogue balloon ends
    {.width = 64, .height = 19, .decode_type = 8, .decode_length = 1216},
    // 11: cyberspace dashboard
    {.width = 320, .height = 200, .decode_type = 3, .decode_length = kFullDecodeLength},
    // 12: database horizon tiles and shapes
    {.width = 320, .height = 200, .decode_type = 7, .decode_length = kFullDecodeLength},
    // 13: more database shapes
    {.width = 320, .height = 200, .decode_type = 3, .decode_length = kFullDecodeLength},
    // 14: ICE, ArmorAll and EEG graphics
    {.width = 320, .height = 200, .decode_type = 8, .decode_length = kFullDecodeLength},
    // 15: unknown use
    {.width = 320, .height = 200, .decode_type = 7, .decode_length = kFullDecodeLength},
});
static_assert(kGameGraphics.size() == 15);

inline constexpr std::uint16_t kAiFaceWidth = 72;
inline constexpr std::uint16_t kAiFaceHeight = 80;

// Decode type of each AI face in bigAIpic, numbered from 1 in file order.
inline constexpr auto kAiFaceTypes = std::to_array<std::uint8_t>({5, 7, 5, 7, 5, 5, 7, 7, 7, 5, 7, 7});
static_assert(kAiFaceTypes.size() == 12);

consteval std::array<PictureLayout, kAiFaceTypes.size()> BuildAiFaces() {
  std::array<PictureLayout, kAiFaceTypes.size()> faces{};
  for (std::size_t index = 0; index < kAiFaceTypes.size(); ++index) {
    faces[index] = PictureLayout{.width = kAiFaceWidth,
                                 .height = kAiFaceHeight,
                                 .decode_type = kAiFaceTypes[index],
                                 .decode_length = std::uint32_t{kAiFaceWidth} * kAiFaceHeight};
  }
  return faces;
}
inline constexpr std::array<PictureLayout, kAiFaceTypes.size()> kAiFaces = BuildAiFaces();

// A decoded picture: one color index per pixel, row-major, and the 32 palette words 0x0RGB.
struct Picture {
  std::uint16_t width{};
  std::uint16_t height{};
  std::vector<std::uint8_t> pixels;
  std::array<std::uint16_t, kPaletteColors> palette{};
};

struct RunLengthResult {
  std::vector<std::uint8_t> data;
  std::size_t consumed_bytes{};
  std::size_t record_bytes{};  // bytes the records describe; more or fewer than data.size() at the edges
};

// Expands run-length records into `size` bytes of planes `row_bytes` wide and `height` tall,
// in row or column order. Bytes past `size` are dropped; bytes no record reaches stay zero.
[[nodiscard]] std::expected<RunLengthResult, DecodeError> DecodeRunLength(std::span<const std::uint8_t> data,
                                                                          std::size_t size, RunLength order,
                                                                          std::size_t row_bytes, std::size_t height);

// XORs every row, from the second down, with the already decoded row above it, plane by plane.
// `planes` holds whole planes of `row_bytes` by `height`.
void XorAdjacentLines(std::span<std::uint8_t> planes, std::size_t row_bytes, std::size_t height);

// One color index per pixel from five planes: bit n of the index comes from plane n.
// `planes` holds exactly five planes of `row_bytes` by `height`.
[[nodiscard]] std::vector<std::uint8_t> PlanarToPixels(std::span<const std::uint8_t> planes, std::size_t row_bytes,
                                                       std::size_t height);

// One color index per chunky byte: the byte's low five bits in reverse order.
[[nodiscard]] std::vector<std::uint8_t> ChunkyToPixels(std::span<const std::uint8_t> bytes);

[[nodiscard]] std::expected<Picture, DecodeError> DecodePicture(std::span<const std::uint8_t> stream,
                                                                const PictureLayout& layout);

}  // namespace newromancer::host
