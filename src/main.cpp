#include <spdlog/spdlog.h>
#include <SFML/Graphics/Color.hpp>
#include <SFML/Graphics/RenderWindow.hpp>
#include <SFML/Window/Event.hpp>
#include <SFML/Window/Keyboard.hpp>
#include <SFML/Window/VideoMode.hpp>
#include <args.hxx>

#include <cstdint>
#include <exception>
#include <iostream>

namespace newromancer {

namespace {

constexpr std::uint32_t kScreenWidth = 320;
constexpr std::uint32_t kScreenHeight = 200;

bool IsCloseRequest(const sf::Event& event) {
  const auto* key = event.getIf<sf::Event::KeyPressed>();
  return event.is<sf::Event::Closed>() or (key != nullptr and key->code == sf::Keyboard::Key::Escape);
}

int Run(std::uint32_t scaling) {
  sf::RenderWindow window{sf::VideoMode{{kScreenWidth * scaling, kScreenHeight * scaling}}, "Neuromancer"};
  window.setVerticalSyncEnabled(true);
  while (window.isOpen()) {
    while (const std::optional<sf::Event> event = window.pollEvent()) {
      if (IsCloseRequest(*event)) {
        window.close();
      }
    }
    window.clear(sf::Color::Black);
    window.display();
  }
  return 0;
}

}  // namespace
}  // namespace newromancer

int main(int argc, char* argv[]) try {
  args::ArgumentParser parser{"Neuromancer", "Native C++23 port of the Amiga version."};
  args::HelpFlag help{parser, "help", "Display this help menu", {'h', "help"}};
  args::ValueFlag<std::uint32_t> scaling{parser, "scaling", "Window scale (1-8)", {'s', "scaling"}, 3};

  int status = 0;
  bool run = true;
  try {
    parser.ParseCLI(argc, argv);
  } catch (const args::Help&) {
    std::cout << parser;
    run = false;
  } catch (const args::ParseError& error) {
    std::cerr << error.what() << '\n' << parser;
    status = 1;
    run = false;
  }
  if (run and (scaling.Get() < 1 or scaling.Get() > 8)) {
    spdlog::error("Window scale must be between 1 and 8.");
    status = 1;
    run = false;
  }
  if (run) {
    status = newromancer::Run(scaling.Get());
  }
  return status;
} catch (const std::exception& error) {
  std::cerr << "Neuromancer: " << error.what() << '\n';
  return 1;
} catch (...) {
  std::cerr << "Neuromancer: unknown error\n";
  return 1;
}
