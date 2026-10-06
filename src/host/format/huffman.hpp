#pragma once

#include <cstddef>
#include <cstdint>
#include <expected>
#include <optional>
#include <span>
#include <vector>

#include "host/format/decode_error.hpp"

namespace newromancer::host {

// A Huffman-coded stream (docs/picture-formats.md, "Huffman streams"): a header with the
// decoded-byte budget, then the code tree and the coded bytes as one bit stream, most
// significant bit first. Decode continues where the previous call stopped; together the calls
// yield at most the budget. The stream views the bytes it was opened on.
class HuffmanStream final {
 public:
  [[nodiscard]] static std::expected<HuffmanStream, DecodeError> Open(std::span<const std::uint8_t> stream);

  // Up to `count` bytes, fewer when the budget runs out first.
  [[nodiscard]] std::expected<std::vector<std::uint8_t>, DecodeError> Decode(std::size_t count);

  [[nodiscard]] std::uint32_t Budget() const { return budget_; }
  [[nodiscard]] std::size_t BitPosition() const { return bit_position_; }

 private:
  // An inner node has no value; its children are indices into nodes_.
  struct Node {
    std::optional<std::uint8_t> value;
    std::uint16_t zero{};
    std::uint16_t one{};
  };

  std::span<const std::uint8_t> stream_;
  std::size_t bit_position_{};
  std::uint32_t budget_{};
  std::vector<Node> nodes_;

  [[nodiscard]] std::optional<std::uint8_t> ReadBits(std::size_t count);
  [[nodiscard]] std::optional<DecodeError> ReadNode(std::size_t index);
};

}  // namespace newromancer::host
