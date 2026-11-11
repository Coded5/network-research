#ifndef PROPAGATIONLAB_CALIBRATED_PATH_LOSS_H
#define PROPAGATIONLAB_CALIBRATED_PATH_LOSS_H

#include "inet/physicallayer/wireless/common/pathloss/FreeSpacePathLoss.h"

namespace propagationlab {

class CalibratedPathLoss : public inet::physicallayer::FreeSpacePathLoss {
public:
  void configure(const std::string &model, double frequency, double systemLoss,
                 double exponent, double referenceDistance,
                 double referenceLoss);
  double receivedPower(double inputDbm, double distance) const;

protected:
  double computePathLoss(inet::mps propagationSpeed, inet::Hz frequency,
                         inet::m distance) const override;

private:
  bool configured = false;
  bool logDistance = false;
  double configuredFrequency = 0;
  double referenceDistance = 1, referenceLoss = 0;
};

} // namespace propagationlab
#endif
