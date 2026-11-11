#include "PropagationLab.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>

namespace propagationlab {
namespace {
constexpr double EPS = 1e-9;
using Point = PropagationLab::Point;
using Obstacle = PropagationLab::Obstacle;
bool finite(Point p) {
  return std::isfinite(p.x) && std::isfinite(p.y) && std::isfinite(p.z);
}
double distance(Point a, Point b) {
  return std::hypot(std::hypot(a.x - b.x, a.y - b.y), a.z - b.z);
}
double cross(double ax, double ay, double bx, double by) {
  return ax * by - ay * bx;
}
bool wallCrosses(Point a, Point b, Point s, Point e, double h) {
  double rx = b.x - a.x, ry = b.y - a.y, sx = e.x - s.x, sy = e.y - s.y;
  double r2 = rx * rx + ry * ry, q2 = sx * sx + sy * sy,
         den = cross(rx, ry, sx, sy);
  if (std::abs(den) <= EPS * std::sqrt(r2 * q2)) {
    if (std::abs(cross(a.x - s.x, a.y - s.y, sx, sy)) > EPS * std::sqrt(q2))
      return false;
    if (r2 <= EPS * EPS) {
      double u = ((a.x - s.x) * sx + (a.y - s.y) * sy) / q2;
      return u >= -EPS && u <= 1 + EPS && std::max(a.z, b.z) >= -EPS &&
             std::min(a.z, b.z) <= h + EPS;
    }
    double t0 = ((s.x - a.x) * rx + (s.y - a.y) * ry) / r2,
           t1 = ((e.x - a.x) * rx + (e.y - a.y) * ry) / r2;
    double lo = std::max(0.0, std::min(t0, t1)),
           hi = std::min(1.0, std::max(t0, t1));
    if (lo > hi + EPS)
      return false;
    double z0 = a.z + lo * (b.z - a.z), z1 = a.z + hi * (b.z - a.z);
    return std::max(z0, z1) >= -EPS && std::min(z0, z1) <= h + EPS;
  }
  double t = cross(s.x - a.x, s.y - a.y, sx, sy) / den,
         u = cross(s.x - a.x, s.y - a.y, rx, ry) / den;
  double z = a.z + t * (b.z - a.z);
  return t >= -EPS && t <= 1 + EPS && u >= -EPS && u <= 1 + EPS && z >= -EPS &&
         z <= h + EPS;
}
bool crosses(Point a, Point b, const Obstacle &o) {
  if (!o.rectangle)
    return wallCrosses(a, b, o.start, o.end, o.height);
  double xmin = std::min(o.start.x, o.end.x),
         xmax = std::max(o.start.x, o.end.x);
  double ymin = std::min(o.start.y, o.end.y),
         ymax = std::max(o.start.y, o.end.y), lo = 0, hi = 1;
  auto clip = [&](double p, double q) {
    if (std::abs(p) <= EPS)
      return q >= -EPS;
    double t = q / p;
    if (p < 0)
      lo = std::max(lo, t);
    else
      hi = std::min(hi, t);
    return lo <= hi + EPS;
  };
  if (!clip(-(b.x - a.x), a.x - xmin) || !clip(b.x - a.x, xmax - a.x) ||
      !clip(-(b.y - a.y), a.y - ymin) || !clip(b.y - a.y, ymax - a.y))
    return false;
  double z0 = a.z + lo * (b.z - a.z), z1 = a.z + hi * (b.z - a.z);
  return std::max(z0, z1) >= -EPS && std::min(z0, z1) <= o.height + EPS;
}
} // namespace

Define_Module(PropagationLab);

std::vector<PropagationLab::Path> PropagationLab::paths(double power, Point a,
                                                        Point b) const {
  std::vector<Path> result;
  auto add = [&](Point bounce, int index, double refl, double first,
                 double second) {
    double d =
        index < 0 ? distance(a, b) : distance(a, bounce) + distance(bounce, b);
    double received = loss->receivedPower(power, d) - first - second - refl;
    if (!std::isfinite(d) || !std::isfinite(received))
      throw omnetpp::cRuntimeError(
          "nonfinite path calculation; check coordinates and model parameters");
    result.push_back({index < 0 ? "direct" : "reflected", index, d, received,
                      refl, first + second, bounce});
  };
  auto leg = [&](Point from, Point to, int reflector, double &total) {
    total = 0;
    for (size_t i = 0; i < obstacles.size(); ++i) {
      const auto &o = obstacles[i];
      if (static_cast<int>(i) == reflector || !crosses(from, to, o))
        continue;
      if (o.blocks)
        return false;
      total += o.attenuation;
    }
    return true;
  };
  double direct = 0;
  if (leg(a, b, -1, direct))
    add({}, -1, 0, direct, 0);
  // ponytail: O(N²) obstacle/path checks per sample; use spatial indexing if
  // scene size grows.
  for (size_t index = 0; index < obstacles.size(); ++index) {
    const auto &o = obstacles[index];
    if (o.reflection < 0)
      continue;
    std::vector<std::pair<Point, Point>> faces;
    if (!o.rectangle)
      faces.emplace_back(o.start, o.end);
    else {
      double xmin = std::min(o.start.x, o.end.x),
             xmax = std::max(o.start.x, o.end.x),
             ymin = std::min(o.start.y, o.end.y),
             ymax = std::max(o.start.y, o.end.y);
      faces.emplace_back(Point{xmin, ymin, 0}, Point{xmax, ymin, 0});
      faces.emplace_back(Point{xmax, ymin, 0}, Point{xmax, ymax, 0});
      faces.emplace_back(Point{xmax, ymax, 0}, Point{xmin, ymax, 0});
      faces.emplace_back(Point{xmin, ymax, 0}, Point{xmin, ymin, 0});
    }
    for (const auto &face : faces) {
      double sx = face.second.x - face.first.x,
             sy = face.second.y - face.first.y, l2 = sx * sx + sy * sy,
             nx = -sy, ny = sx;
      double sideA = (a.x - face.first.x) * nx + (a.y - face.first.y) * ny,
             sideB = (b.x - face.first.x) * nx + (b.y - face.first.y) * ny;
      if (o.rectangle ? (sideA >= -EPS || sideB >= -EPS)
                      : (sideA * sideB <= EPS))
        continue;
      double projection = sideA / l2;
      Point image{a.x - 2 * projection * nx, a.y - 2 * projection * ny, a.z};
      double rayX = b.x - image.x, rayY = b.y - image.y,
             den = cross(rayX, rayY, sx, sy);
      if (std::abs(den) <= EPS)
        continue;
      double t =
          cross(face.first.x - image.x, face.first.y - image.y, sx, sy) / den;
      double u =
          cross(face.first.x - image.x, face.first.y - image.y, rayX, rayY) /
          den;
      if (t <= EPS || t >= 1 - EPS || u <= EPS || u >= 1 - EPS)
        continue;
      Point bounce{image.x + t * rayX, image.y + t * rayY,
                   a.z + t * (b.z - a.z)};
      if (bounce.z < 0 || bounce.z > o.height)
        continue;
      double first = 0, second = 0;
      if (leg(a, bounce, index, first) && leg(bounce, b, index, second))
        add(bounce, index, o.reflection, first, second);
    }
  }
  return result;
}

void PropagationLab::initialize() {
  loss = omnetpp::check_and_cast<CalibratedPathLoss *>(
      getParentModule()->getSubmodule("pathLoss"));
  std::cout << "PLAB READY 1\n" << std::flush;
  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream in(line);
    std::string command;
    in >> command;
    if (command == "QUIT") {
      std::string extra;
      if (in >> extra)
        throw omnetpp::cRuntimeError("malformed QUIT");
      return;
    }
    if (command == "CONFIG") {
      std::string model;
      double x, y, z, input, freq, sys, exp, d0, ref;
      int count;
      std::string extra;
      if (!(in >> model >> x >> y >> z >> input >> freq >> sys >> exp >> d0 >>
            ref >> count) ||
          (in >> extra) || count < 0 || count > 32 || !finite({x, y, z}) ||
          !std::isfinite(input))
        throw omnetpp::cRuntimeError("malformed CONFIG");
      std::vector<Obstacle> next;
      for (int i = 0; i < count; ++i) {
        if (!std::getline(std::cin, line))
          throw omnetpp::cRuntimeError("truncated obstacle list");
        std::istringstream row(line);
        int rectangle, blocks;
        Obstacle o{};
        if (!(row >> rectangle >> o.start.x >> o.start.y >> o.end.x >>
              o.end.y >> o.height >> blocks >> o.attenuation >> o.reflection) ||
            (row >> extra) || !(rectangle == 0 || rectangle == 1) ||
            !(blocks == 0 || blocks == 1))
          throw omnetpp::cRuntimeError("malformed obstacle");
        o.rectangle = rectangle;
        o.blocks = blocks;
        double width = std::abs(o.end.x - o.start.x),
               depth = std::abs(o.end.y - o.start.y);
        if (!finite(o.start) || !finite(o.end) ||
            (rectangle ? (width <= EPS || depth <= EPS)
                       : (std::hypot(width, depth) <= EPS)) ||
            !std::isfinite(o.height) || o.height <= 0 || o.height > 10000 ||
            !std::isfinite(o.attenuation) || o.attenuation < 0 ||
            o.attenuation > 300 || !std::isfinite(o.reflection) ||
            (o.reflection < 0 && o.reflection != -1) || o.reflection > 300 ||
            (!blocks && o.reflection >= 0 &&
             std::pow(10., -o.attenuation / 10.) +
                     std::pow(10., -o.reflection / 10.) >
                 1. + 1e-12))
          throw omnetpp::cRuntimeError("invalid obstacle geometry or material");
        next.push_back(o);
      }
      if (!finite({x, y, z}) || !std::isfinite(input))
        throw omnetpp::cRuntimeError("invalid transmitter");
      loss->configure(model, freq, sys, exp, d0, ref);
      txPower = input;
      txPosition = {x, y, z};
      obstacles = std::move(next);
      configured = true;
      std::cout << "PLAB OK\n" << std::flush;
      continue;
    }
    if (command == "POWER") {
      double x, y, z;
      int include;
      std::string extra;
      if (!(in >> x >> y >> z >> include) || (in >> extra) ||
          !finite({x, y, z}) || (include != 0 && include != 1))
        throw omnetpp::cRuntimeError("malformed POWER");
      if (!configured)
        throw omnetpp::cRuntimeError("CONFIG must precede POWER");
      auto found = paths(txPower, txPosition, {x, y, z});
      double maximum = -std::numeric_limits<double>::infinity(), sum = 0;
      for (const auto &p : found)
        maximum = std::max(maximum, p.power);
      if (!found.empty()) {
        for (const auto &p : found)
          sum += std::pow(10., (p.power - maximum) / 10.);
        maximum += 10 * std::log10(sum);
      }
      std::cout << std::setprecision(17) << "PLAB POWER " << maximum << " "
                << found.size() << "\n";
      if (include)
        for (const auto &p : found)
          std::cout << "PLAB PATH " << p.kind << " " << p.index << " "
                    << p.distance << " " << p.power << " " << p.reflection
                    << " " << p.transmission << " " << p.bounce.x << " "
                    << p.bounce.y << " " << p.bounce.z << "\n";
      std::cout << "PLAB END\n" << std::flush;
      continue;
    }
    throw omnetpp::cRuntimeError("unknown protocol command");
  }
}

} // namespace propagationlab
