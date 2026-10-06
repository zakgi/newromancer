#include "host/format/huffman.hpp"

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

// Writes bits most significant first and pads the result to whole 16-bit words.
class BitWriter final {
 public:
  void Write(std::uint32_t value, std::size_t count) {
    for (std::size_t index = count; index > 0; --index) {
      bits_.push_back(((value >> (index - 1)) & 1) != 0);
    }
  }

  [[nodiscard]] std::size_t Size() const { return bits_.size(); }

  [[nodiscard]] std::vector<std::uint8_t> Bytes() const {
    std::vector<std::uint8_t> bytes((bits_.size() + 15) / 16 * 2, 0);
    for (std::size_t index = 0; index < bits_.size(); ++index) {
      if (bits_[index]) {
        bytes[index / 8] |= static_cast<std::uint8_t>(0x80 >> (index % 8));
      }
    }
    return bytes;
  }

 private:
  std::vector<bool> bits_;
};

// A complete depth-8 code tree whose code for each byte is the byte itself.
void WriteFullTree(BitWriter& writer, std::uint32_t prefix = 0, std::size_t depth = 0) {
  if (depth == 8) {
    writer.Write(1, 1);
    writer.Write(prefix, 8);
  } else {
    writer.Write(0, 1);
    WriteFullTree(writer, prefix * 2, depth + 1);
    writer.Write(0, 1);
    WriteFullTree(writer, (prefix * 2) + 1, depth + 1);
  }
}

std::vector<std::uint8_t> Stream(std::uint32_t budget, const BitWriter& writer) {
  std::vector<std::uint8_t> stream{static_cast<std::uint8_t>(budget >> 24),
                                   static_cast<std::uint8_t>(budget >> 16),
                                   static_cast<std::uint8_t>(budget >> 8),
                                   static_cast<std::uint8_t>(budget),
                                   0,
                                   0,
                                   0,
                                   0};
  const std::vector<std::uint8_t> bits = writer.Bytes();
  stream.insert(stream.end(), bits.begin(), bits.end());
  return stream;
}

std::vector<std::uint8_t> EncodeStream(std::span<const std::uint8_t> data, std::optional<std::uint32_t> budget = {}) {
  BitWriter writer;
  WriteFullTree(writer);
  for (const std::uint8_t value : data) {
    writer.Write(value, 8);
  }
  return Stream(budget ? *budget : static_cast<std::uint32_t>(data.size()), writer);
}

}  // namespace

TEST(HuffmanTest, SuccessiveDecodesContinueTheStream) {
  std::vector<std::uint8_t> data(256);
  for (std::size_t index = 0; index < data.size(); ++index) {
    data[index] = static_cast<std::uint8_t>(index);
  }
  const std::vector<std::uint8_t> encoded = EncodeStream(data);
  std::expected<HuffmanStream, DecodeError> stream = HuffmanStream::Open(encoded);
  ASSERT_TRUE(stream);
  const std::expected<std::vector<std::uint8_t>, DecodeError> first = stream->Decode(10);
  const std::expected<std::vector<std::uint8_t>, DecodeError> rest = stream->Decode(1000);
  const std::expected<std::vector<std::uint8_t>, DecodeError> after = stream->Decode(5);
  ASSERT_TRUE(first and rest and after);
  EXPECT_EQ(*first, std::vector<std::uint8_t>(data.begin(), data.begin() + 10));
  EXPECT_EQ(*rest, std::vector<std::uint8_t>(data.begin() + 10, data.end()));
  EXPECT_TRUE(after->empty());
}

TEST(HuffmanTest, BudgetLimitsTheOutput) {
  constexpr std::array<std::uint8_t, 3> kData{'a', 'b', 'c'};
  const std::vector<std::uint8_t> encoded = EncodeStream(kData, 2);
  std::expected<HuffmanStream, DecodeError> stream = HuffmanStream::Open(encoded);
  ASSERT_TRUE(stream);
  const std::expected<std::vector<std::uint8_t>, DecodeError> decoded = stream->Decode(10);
  ASSERT_TRUE(decoded);
  EXPECT_EQ(*decoded, (std::vector<std::uint8_t>{'a', 'b'}));
  EXPECT_EQ(stream->Budget(), 0U);
}

TEST(HuffmanTest, SingleLeafTreeNeedsNoBits) {
  BitWriter writer;
  writer.Write(1, 1);
  writer.Write('A', 8);
  const std::vector<std::uint8_t> encoded = Stream(3, writer);
  std::expected<HuffmanStream, DecodeError> stream = HuffmanStream::Open(encoded);
  ASSERT_TRUE(stream);
  const std::expected<std::vector<std::uint8_t>, DecodeError> decoded = stream->Decode(3);
  ASSERT_TRUE(decoded);
  EXPECT_EQ(*decoded, (std::vector<std::uint8_t>{'A', 'A', 'A'}));
}

TEST(HuffmanTest, RejectsStreamsThatRunOut) {
  constexpr std::array<std::uint8_t, 6> kData{'a', 'b', 'c', 'd', 'e', 'f'};
  std::vector<std::uint8_t> encoded = EncodeStream(kData);
  encoded.resize(encoded.size() - 4);
  std::expected<HuffmanStream, DecodeError> stream = HuffmanStream::Open(encoded);
  ASSERT_TRUE(stream);
  const std::expected<std::vector<std::uint8_t>, DecodeError> decoded = stream->Decode(6);
  ASSERT_FALSE(decoded);
  EXPECT_EQ(decoded.error(), DecodeError::TruncatedStream);

  constexpr std::array<std::uint8_t, 7> kShort{};
  const std::expected<HuffmanStream, DecodeError> header = HuffmanStream::Open(kShort);
  ASSERT_FALSE(header);
  EXPECT_EQ(header.error(), DecodeError::TruncatedHeader);
}

TEST(HuffmanTest, RejectsOversizedTrees) {
  BitWriter writer;
  writer.Write(0, 300);
  const std::vector<std::uint8_t> encoded = Stream(1, writer);
  const std::expected<HuffmanStream, DecodeError> stream = HuffmanStream::Open(encoded);
  ASSERT_FALSE(stream);
  EXPECT_EQ(stream.error(), DecodeError::TreeTooLarge);
}

// Every picture stream decodes its whole budget within its bits; the digest of all decoded
// bytes matches the Python reference.
TEST(HuffmanTest, DecodesEveryPictureStreamOfTheOriginalDisk) {
  AdfImageManager disk;
  if (not disk.AddDiskImage(std::filesystem::path{NEWROMANCER_ADF})) {
    GTEST_SKIP() << "game disk not present at " << NEWROMANCER_ADF;
  }
  std::vector<std::uint8_t> decoded;
  std::size_t stream_count = 0;
  for (const std::string_view name : {"bigpic0158", "bigpic2", "bigAIpic"}) {
    const std::optional<std::span<const std::uint8_t>> file = disk.GetFile(name);
    ASSERT_TRUE(file) << name;
    const std::expected<std::vector<std::span<const std::uint8_t>>, DecodeError> entries = ReadEntries(*file);
    ASSERT_TRUE(entries) << name;
    for (const std::span<const std::uint8_t> entry : *entries) {
      std::expected<HuffmanStream, DecodeError> stream = HuffmanStream::Open(entry);
      ASSERT_TRUE(stream) << name;
      const std::expected<std::vector<std::uint8_t>, DecodeError> bytes = stream->Decode(stream->Budget());
      ASSERT_TRUE(bytes) << name;
      EXPECT_LE((entry.size() * 8) - stream->BitPosition(), 7U) << name;
      decoded.insert(decoded.end(), bytes->begin(), bytes->end());
      ++stream_count;
    }
  }
  EXPECT_EQ(stream_count, 82U);
  EXPECT_EQ(test::Sha256Hex(decoded), "624f6123087ff58b8e15c602afa4c4048cdf4ce7cf12fbd262a0058564d948f2");
}

}  // namespace newromancer::host
