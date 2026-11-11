#ifndef PROPAGATIONLAB_CONTROLLER_H
#define PROPAGATIONLAB_CONTROLLER_H

#include "CalibratedPathLoss.h"
#include <omnetpp.h>
#include <vector>

namespace propagationlab {

class PropagationLab : public omnetpp::cSimpleModule {
public:
  struct Point {
    double x, y, z;
  };
  struct Obstacle {
    bool rectangle, blocks;
    Point start, end;
    double height, attenuation, reflection;
  };
  struct Path {
    const char *kind;
    int index;
    double distance, power, reflection, transmission;
    Point bounce;
  };

protected:
  void initialize() override;

private:
  std::vector<Path> paths(double power, Point a, Point b) const;
  CalibratedPathLoss *loss = nullptr;
  std::vector<Obstacle> obstacles;
  double txPower = 0;
  Point txPosition{};
  bool configured = false;
};

} // namespace propagationlab
#endif
