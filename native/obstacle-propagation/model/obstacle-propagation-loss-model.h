#ifndef OBSTACLE_PROPAGATION_LOSS_MODEL_H
#define OBSTACLE_PROPAGATION_LOSS_MODEL_H

#include "ns3/propagation-loss-model.h"
#include "ns3/vector.h"

#include <string>
#include <vector>

namespace ns3
{

struct ReflectionPath
{
    std::string kind;
    int obstacleIndex{-1};
    double distanceM{0.0};
    double rxPowerDbm{0.0};
    double reflectionLossDb{0.0};
    double transmissionLossDb{0.0};
    Vector bounce{0.0, 0.0, 0.0};
};

class ObstaclePropagationLossModel : public PropagationLossModel
{
  public:
    struct Obstacle
    {
        bool rectangle;
        Vector start;
        Vector end;
        double height;
        bool blocks;
        double attenuation;
        double reflection;
    };

    static TypeId GetTypeId();
    void SetBaseModel(Ptr<PropagationLossModel> model);
    void AddObstacle(bool rectangle,
                     Vector start,
                     Vector end,
                     double heightM,
                     bool blocks,
                     double attenuationDb,
                     double reflectionLossDb);
    std::vector<ReflectionPath> GetPaths(double txPowerDbm,
                                         Ptr<MobilityModel> tx,
                                         Ptr<MobilityModel> rx) const;

  private:
    double DoCalcRxPower(double txPowerDbm,
                         Ptr<MobilityModel> tx,
                         Ptr<MobilityModel> rx) const override;
    int64_t DoAssignStreams(int64_t stream) override;
    Ptr<PropagationLossModel> m_base;
    std::vector<Obstacle> m_obstacles;
};

} // namespace ns3

#endif
