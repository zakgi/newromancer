#include "host/format/picture.hpp"

#include <gtest/gtest.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <expected>
#include <filesystem>
#include <optional>
#include <span>
#include <string_view>
#include <vector>

#include "host/adf.hpp"
#include "host/format/offset_table.hpp"
#include "sha256.hpp"

namespace newromancer::host {
namespace {

using Expanded = std::expected<RunLengthResult, DecodeError>;
using Decoded = std::expected<Picture, DecodeError>;

// A stream whose code tree is a single leaf: every decoded byte is `value`, and decoding
// consumes no bits beyond the tree.
std::vector<std::uint8_t> SingleValueStream(std::uint8_t value, std::uint32_t budget) {
  return {static_cast<std::uint8_t>(budget >> 24),
          static_cast<std::uint8_t>(budget >> 16),
          static_cast<std::uint8_t>(budget >> 8),
          static_cast<std::uint8_t>(budget),
          0,
          0,
          0,
          0,
          static_cast<std::uint8_t>(0x80 | (value >> 1)),
          static_cast<std::uint8_t>((value & 1) << 7)};
}

void AppendBigEndianU16(std::vector<std::uint8_t>& bytes, std::uint16_t value) {
  bytes.push_back(static_cast<std::uint8_t>(value >> 8));
  bytes.push_back(static_cast<std::uint8_t>(value));
}

}  // namespace

TEST(RunLengthTest, RowsRepeatAndCopy) {
  constexpr std::array<std::uint8_t, 6> kRecords{3, 7, 0x82, 1, 2, 0};
  const Expanded result = DecodeRunLength(kRecords, 5, RunLength::Rows, 5, 1);
  ASSERT_TRUE(result);
  EXPECT_EQ(result->data, (std::vector<std::uint8_t>{7, 7, 7, 1, 2}));
  EXPECT_EQ(result->consumed_bytes, 5U);
  EXPECT_EQ(result->record_bytes, 5U);
}

TEST(RunLengthTest, BothEndMarkersLeaveZeros) {
  constexpr std::array<std::uint8_t, 2> kMarkers{0x00, 0x80};
  for (const std::uint8_t marker : kMarkers) {
    const std::array<std::uint8_t, 3> records{2, 9, marker};
    const Expanded result = DecodeRunLength(records, 4, RunLength::Rows, 4, 1);
    ASSERT_TRUE(result) << marker;
    EXPECT_EQ(result->data, (std::vector<std::uint8_t>{9, 9, 0, 0}));
    EXPECT_EQ(result->consumed_bytes, 3U);
    EXPECT_EQ(result->record_bytes, 2U);
  }
}

TEST(RunLengthTest, ExcessBytesAreDropped) {
  constexpr std::array<std::uint8_t, 2> kRecords{5, 4};
  const Expanded result = DecodeRunLength(kRecords, 3, RunLength::Rows, 3, 1);
  ASSERT_TRUE(result);
  EXPECT_EQ(result->data, (std::vector<std::uint8_t>{4, 4, 4}));
  EXPECT_EQ(result->record_bytes, 5U);
}

TEST(RunLengthTest, ColumnsFillTopToBottom) {
  constexpr std::array<std::uint8_t, 5> kRecords{0x84, 1, 2, 3, 4};
  const Expanded result = DecodeRunLength(kRecords, 4, RunLength::Columns, 2, 2);
  ASSERT_TRUE(result);
  EXPECT_EQ(result->data, (std::vector<std::uint8_t>{1, 3, 2, 4}));
}

TEST(RunLengthTest, RejectsTruncatedRecordsAndMissingOrder) {
  constexpr std::array<std::uint8_t, 2> kLiteral{0x83, 1};
  const Expanded literal = DecodeRunLength(kLiteral, 4, RunLength::Rows, 4, 1);
  ASSERT_FALSE(literal);
  EXPECT_EQ(literal.error(), DecodeError::TruncatedRecord);

  constexpr std::array<std::uint8_t, 2> kShort{2, 1};
  const Expanded ends_early = DecodeRunLength(kShort, 4, RunLength::Rows, 4, 1);
  ASSERT_FALSE(ends_early);
  EXPECT_EQ(ends_early.error(), DecodeError::TruncatedRecord);

  const Expanded no_order = DecodeRunLength(kShort, 4, RunLength::None, 4, 1);
  ASSERT_FALSE(no_order);
  EXPECT_EQ(no_order.error(), DecodeError::BadLayout);
}

TEST(PixelTest, XorLinesAccumulateDownEachPlane) {
  std::array<std::uint8_t, 6> planes{1, 2, 3, 4, 5, 6};
  XorAdjacentLines(planes, 2, 3);
  EXPECT_EQ(planes, (std::array<std::uint8_t, 6>{1, 2, 2, 6, 7, 0}));
}

TEST(PixelTest, PlaneNSuppliesBitN) {
  constexpr std::array<std::uint8_t, 5> kPlanes{0x80, 0x80, 0x01, 0x01, 0x01};
  EXPECT_EQ(PlanarToPixels(kPlanes, 1, 1), (std::vector<std::uint8_t>{3, 0, 0, 0, 0, 0, 0, 28}));
}

TEST(PixelTest, ChunkyBytesReverseTheirLowFiveBits) {
  constexpr std::array<std::uint8_t, 4> kBytes{0x01, 0x10, 0x17, 0xE1};
  EXPECT_EQ(ChunkyToPixels(kBytes), (std::vector<std::uint8_t>{0x10, 0x01, 0x1D, 0x10}));
}

TEST(PictureTest, DecodesPlanarPictureWithPalette) {
  const std::vector<std::uint8_t> stream = SingleValueStream(0xFF, kPaletteBytes + 5);
  const Decoded picture =
      DecodePicture(stream, PictureLayout{.width = 8, .height = 1, .decode_type = 0, .decode_length = 5});
  ASSERT_TRUE(picture);
  EXPECT_EQ(picture->width, 8);
  EXPECT_EQ(picture->height, 1);
  EXPECT_EQ(picture->pixels, std::vector<std::uint8_t>(8, 31));
  for (const std::uint16_t color : picture->palette) {
    EXPECT_EQ(color, 0xFFFF);
  }
}

TEST(PictureTest, DecodesChunkyRunLengthPicture) {
  // Every data byte is 0x81: a one-byte literal record holding 0x81, whose color index is 0x10.
  const std::vector<std::uint8_t> stream = SingleValueStream(0x81, kPaletteBytes + 4);
  const Decoded picture =
      DecodePicture(stream, PictureLayout{.width = 2, .height = 1, .decode_type = 7, .decode_length = 4});
  ASSERT_TRUE(picture);
  EXPECT_EQ(picture->pixels, (std::vector<std::uint8_t>{0x10, 0x10}));
}

TEST(PictureTest, RejectsUnknownTypesBadLayoutsAndShortStreams) {
  const std::vector<std::uint8_t> stream = SingleValueStream(0, kPaletteBytes + 4);
  const Decoded unknown =
      DecodePicture(stream, PictureLayout{.width = 8, .height = 1, .decode_type = 9, .decode_length = 4});
  ASSERT_FALSE(unknown);
  EXPECT_EQ(unknown.error(), DecodeError::UnknownDecodeType);

  const Decoded odd_width =
      DecodePicture(stream, PictureLayout{.width = 12, .height = 1, .decode_type = 0, .decode_length = 4});
  ASSERT_FALSE(odd_width);
  EXPECT_EQ(odd_width.error(), DecodeError::BadLayout);

  const Decoded short_data =
      DecodePicture(stream, PictureLayout{.width = 8, .height = 1, .decode_type = 0, .decode_length = 4});
  ASSERT_FALSE(short_data);
  EXPECT_EQ(short_data.error(), DecodeError::TruncatedPicture);

  const Decoded no_header = DecodePicture(std::span<const std::uint8_t>{},
                                          PictureLayout{.width = 8, .height = 1, .decode_type = 0, .decode_length = 4});
  ASSERT_FALSE(no_header);
  EXPECT_EQ(no_header.error(), DecodeError::TruncatedHeader);
}

// Every picture of the original disk decodes; the digest of all sizes, pixels and palettes
// matches the Python reference.
TEST(PictureTest, DecodesEveryPictureOfTheOriginalDisk) {
  AdfImageManager disk;
  if (not disk.AddDiskImage(std::filesystem::path{NEWROMANCER_ADF})) {
    GTEST_SKIP() << "game disk not present at " << NEWROMANCER_ADF;
  }
  std::vector<PictureLayout> layouts;
  layouts.reserve(kRoomPictures.size() + kGameGraphics.size() + kAiFaces.size());
  for (const RoomPicture& room : kRoomPictures) {
    layouts.push_back(room.layout);
  }
  layouts.insert(layouts.end(), kGameGraphics.begin(), kGameGraphics.end());
  layouts.insert(layouts.end(), kAiFaces.begin(), kAiFaces.end());
  std::vector<std::span<const std::uint8_t>> streams;
  for (const std::string_view name : {"bigpic0158", "bigpic2", "bigAIpic"}) {
    const std::optional<std::span<const std::uint8_t>> file = disk.GetFile(name);
    ASSERT_TRUE(file) << name;
    const std::expected<std::vector<std::span<const std::uint8_t>>, DecodeError> entries = ReadEntries(*file);
    ASSERT_TRUE(entries) << name;
    streams.insert(streams.end(), entries->begin(), entries->end());
  }
  ASSERT_EQ(streams.size(), 82U);
  ASSERT_EQ(layouts.size(), streams.size());
  std::vector<std::uint8_t> decoded;
  for (std::size_t index = 0; index < streams.size(); ++index) {
    const Decoded picture = DecodePicture(streams[index], layouts[index]);
    ASSERT_TRUE(picture) << "picture " << index;
    AppendBigEndianU16(decoded, picture->width);
    AppendBigEndianU16(decoded, picture->height);
    decoded.insert(decoded.end(), picture->pixels.begin(), picture->pixels.end());
    for (const std::uint16_t color : picture->palette) {
      AppendBigEndianU16(decoded, color);
    }
  }
  EXPECT_EQ(test::Sha256Hex(decoded), "7ee36d7134f90db8be5344167ac5ca14d699aedf9dd5f25cefea4f8b28c2c92c");
}

}  // namespace newromancer::host
