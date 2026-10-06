#include "host/format/huffman.hpp"

#include <algorithm>
#include <utility>

#include "host/format/big_endian.hpp"

namespace newromancer::host {

namespace {

constexpr std::size_t kHeaderSize = 8;
constexpr std::size_t kValueBits = 8;
// A tree over the 256 byte values has at most 255 inner nodes and 256 leaves.
constexpr std::size_t kMaxNodes = 511;

}  // namespace

std::expected<HuffmanStream, DecodeError> HuffmanStream::Open(std::span<const std::uint8_t> stream) {
  std::optional<DecodeError> error;
  HuffmanStream huffman;
  if (stream.size() < kHeaderSize) {
    error = DecodeError::TruncatedHeader;
  } else {
    huffman.stream_ = stream;
    huffman.budget_ = ReadBigEndianU32(stream, 0);
    huffman.bit_position_ = kHeaderSize * 8;
    huffman.nodes_.emplace_back();
    error = huffman.ReadNode(0);
  }
  std::expected<HuffmanStream, DecodeError> outcome;
  if (error) {
    outcome = std::unexpected{*error};
  } else {
    outcome = std::move(huffman);
  }
  return outcome;
}

std::expected<std::vector<std::uint8_t>, DecodeError> HuffmanStream::Decode(std::size_t count) {
  std::optional<DecodeError> error;
  const std::size_t length = std::min<std::size_t>(count, budget_);
  std::vector<std::uint8_t> bytes;
  bytes.reserve(length);
  while (bytes.size() < length and not error) {
    std::size_t node = 0;
    while (not nodes_[node].value and not error) {
      if (const std::optional<std::uint8_t> bit = ReadBits(1)) {
        node = *bit == 0 ? nodes_[node].zero : nodes_[node].one;
      } else {
        error = DecodeError::TruncatedStream;
      }
    }
    if (not error) {
      bytes.push_back(*nodes_[node].value);
    }
  }
  std::expected<std::vector<std::uint8_t>, DecodeError> outcome;
  if (error) {
    outcome = std::unexpected{*error};
  } else {
    budget_ -= static_cast<std::uint32_t>(length);
    outcome = std::move(bytes);
  }
  return outcome;
}

std::optional<std::uint8_t> HuffmanStream::ReadBits(std::size_t count) {
  std::optional<std::uint8_t> bits;
  if (bit_position_ + count <= stream_.size() * 8) {
    std::uint8_t value = 0;
    for (std::size_t index = 0; index < count; ++index) {
      const std::uint8_t byte = stream_[bit_position_ / 8];
      value = static_cast<std::uint8_t>(value << 1 | ((byte >> (7 - bit_position_ % 8)) & 1));
      ++bit_position_;
    }
    bits = value;
  }
  return bits;
}

// Pre-order: bit 1 is a leaf followed by its value; bit 0 is an inner node followed by its
// zero subtree, one bit the reader skips, and its one subtree.
std::optional<DecodeError> HuffmanStream::ReadNode(std::size_t index) {
  std::optional<DecodeError> error;
  const std::optional<std::uint8_t> kind = ReadBits(1);
  if (not kind) {
    error = DecodeError::TruncatedStream;
  } else if (*kind == 1) {
    nodes_[index].value = ReadBits(kValueBits);
    if (not nodes_[index].value) {
      error = DecodeError::TruncatedStream;
    }
  } else if (nodes_.size() + 2 > kMaxNodes) {
    error = DecodeError::TreeTooLarge;
  } else {
    const auto zero = static_cast<std::uint16_t>(nodes_.size());
    const auto one = static_cast<std::uint16_t>(zero + 1);
    nodes_[index].zero = zero;
    nodes_[index].one = one;
    nodes_.resize(nodes_.size() + 2);
    error = ReadNode(zero);
    if (not error and not ReadBits(1)) {
      error = DecodeError::TruncatedStream;
    }
    if (not error) {
      error = ReadNode(one);
    }
  }
  return error;
}

}  // namespace newromancer::host
