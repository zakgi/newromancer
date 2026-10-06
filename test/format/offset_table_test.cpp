#include "host/format/offset_table.hpp"

#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <expected>
#include <span>
#include <vector>

namespace newromancer::host {
namespace {

using Entries = std::expected<std::vector<std::span<const std::uint8_t>>, DecodeError>;

TEST(OffsetTableTest, EntriesRunToTheNextOffsetAndTheEnd) {
  constexpr std::array<std::uint8_t, 16> kData{0, 0, 0, 12, 0, 0, 0, 14, 0, 0, 0, 0, 'a', 'b', 'c', 'd'};
  const Entries entries = ReadEntries(kData);
  ASSERT_TRUE(entries);
  ASSERT_EQ(entries->size(), 2U);
  EXPECT_EQ((*entries)[0].size(), 2U);
  EXPECT_EQ((*entries)[0][0], 'a');
  EXPECT_EQ((*entries)[1].size(), 2U);
  EXPECT_EQ((*entries)[1][0], 'c');
}

TEST(OffsetTableTest, RejectsMissingTerminator) {
  constexpr std::array<std::uint8_t, 4> kData{0, 0, 0, 8};
  const Entries entries = ReadEntries(kData);
  ASSERT_FALSE(entries);
  EXPECT_EQ(entries.error(), DecodeError::TruncatedTable);
}

TEST(OffsetTableTest, RejectsOffsetsOutsideTheData) {
  constexpr std::array<std::uint8_t, 10> kIntoTable{0, 0, 0, 4, 0, 0, 0, 0, 'x', 'x'};
  const Entries into_table = ReadEntries(kIntoTable);
  ASSERT_FALSE(into_table);
  EXPECT_EQ(into_table.error(), DecodeError::OffsetOutOfRange);

  constexpr std::array<std::uint8_t, 10> kPastEnd{0, 0, 0, 10, 0, 0, 0, 0, 'x', 'x'};
  const Entries past_end = ReadEntries(kPastEnd);
  ASSERT_FALSE(past_end);
  EXPECT_EQ(past_end.error(), DecodeError::OffsetOutOfRange);
}

}  // namespace
}  // namespace newromancer::host
