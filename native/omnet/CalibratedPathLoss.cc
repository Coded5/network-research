#include "CalibratedPathLoss.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace propagationlab {

Define_Module(CalibratedPathLoss);

void CalibratedPathLoss::configure(const std::string &model, double frequency,
                                   double loss, double exponent, double d0,
                                   double refLoss) {
  if (!std::isfinite(frequency) || frequency <= 0 || frequency > 1e12 ||
      !std::isfinite(loss) || loss < 1 || !std::isfinite(exponent) ||
      exponent <= 0 || exponent > 10 || !std::isfinite(d0) || d0 <= 0 ||
      !std::isfinite(refLoss) || refLoss < 0 || refLoss > 300) {
    throw std::invalid_argument("invalid path-loss parameters");
  }
  if (model != "friis" && model != "log_distance") {
    throw std::invalid_argument("unknown path-loss model");
  }

  logDistance = model == "log_distance";
  configuredFrequency = frequency;
  referenceDistance = d0;
  referenceLoss = refLoss;
  alpha = logDistance ? exponent : 2;
  systemLoss = logDistance ? 1 : loss;
  configured = true;
}

double CalibratedPathLoss::computePathLoss(inet::mps speed, inet::Hz frequency,
                                           inet::m distance) const {
  if (!logDistance)
    return std::min(
        1.0, FreeSpacePathLoss::computePathLoss(speed, frequency, distance));

  const auto at = [&](double d) {
    return FreeSpacePathLoss::computePathLoss(
        inet::mps(299792458), inet::Hz(configuredFrequency), inet::m(d));
  };
  if (distance.get() <= referenceDistance)
    return std::pow(10.0, -referenceLoss / 10.0);

  const double gain = at(distance.get());
  const double referenceGain = at(referenceDistance);
  if (!std::isfinite(gain) || gain <= 0 || !std::isfinite(referenceGain) ||
      referenceGain <= 0)
    throw omnetpp::cRuntimeError("invalid INET path-loss gain");
  return std::pow(10.0, -referenceLoss / 10.0) * gain / referenceGain;
}

double CalibratedPathLoss::receivedPower(double inputDbm,
                                         double distance) const {
  if (!configured)
    throw omnetpp::cRuntimeError("path-loss model is not configured");
  if (!std::isfinite(inputDbm) || !std::isfinite(distance) || distance < 0) {
    throw std::invalid_argument(
        "finite power and nonnegative distance required");
  }

  if (logDistance) {
    if (distance <= referenceDistance)
      return inputDbm - referenceLoss;
    const double gainD = FreeSpacePathLoss::computePathLoss(
        inet::mps(299792458), inet::Hz(configuredFrequency), inet::m(distance));
    const double gainD0 = FreeSpacePathLoss::computePathLoss(
        inet::mps(299792458), inet::Hz(configuredFrequency),
        inet::m(referenceDistance));
    if (!std::isfinite(gainD) || gainD <= 0 || !std::isfinite(gainD0) ||
        gainD0 <= 0)
      throw omnetpp::cRuntimeError("invalid INET path-loss gain");
    return inputDbm - referenceLoss + 10 * std::log10(gainD) -
           10 * std::log10(gainD0);
  }

  const double gain = computePathLoss(
      inet::mps(299792458), inet::Hz(configuredFrequency), inet::m(distance));
  if (!std::isfinite(gain) || gain <= 0)
    throw omnetpp::cRuntimeError("invalid INET path-loss gain");
  return inputDbm + 10 * std::log10(gain);
}

} // namespace propagationlab
