#include "host/adf.hpp"

#include <gtest/gtest.h>

#include <filesystem>

namespace newromancer::host {
namespace {

std::filesystem::path DiskImage() {
  return std::filesystem::path{NEWROMANCER_ADF};
}

TEST(Adf, FindsFilesWhateverTheCase) {
  auto disk = AdfImageManager{};
  if (not disk.AddDiskImage(DiskImage())) {
    GTEST_SKIP() << "game disk not present at " << DiskImage();
  }
  // The disk has bigpic0158 and s/startup-sequence.
  EXPECT_TRUE(disk.GetFile("BIGPIC0158").has_value());
  EXPECT_TRUE(disk.GetFile("S/Startup-Sequence").has_value());
  EXPECT_FALSE(disk.GetFile("MISSING.BIN").has_value());
  EXPECT_EQ(disk.GetFile("kurt1")->size(), 1'606U);
  EXPECT_EQ(disk.GetFile("bigpic0158")->size(), 313'625U);
  EXPECT_EQ(disk.GetFile("NEURO")->size(), 142'820U);
}

TEST(Adf, RefusesAMissingImage) {
  auto disk = AdfImageManager{};
  EXPECT_FALSE(disk.AddDiskImage(DiskImage().parent_path() / "missing.adf"));
  EXPECT_FALSE(disk.GetFile("NEURO").has_value());
}

}  // namespace
}  // namespace newromancer::host
