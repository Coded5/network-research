#include "obstacle-propagation-loss-model.h"

#include "ns3/constant-position-mobility-model.h"
#include "ns3/mobility-model.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace ns3
{
namespace
{
constexpr double EPS = 1e-9;

bool Finite(const Vector& p)
{
    return std::isfinite(p.x) && std::isfinite(p.y) && std::isfinite(p.z);
}

double Distance(const Vector& a, const Vector& b)
{
    return std::hypot(std::hypot(a.x - b.x, a.y - b.y), a.z - b.z);
}

double Cross(double ax, double ay, double bx, double by)
{
    return ax * by - ay * bx;
}

bool WallCrosses(const Vector& a, const Vector& b, const Vector& s, const Vector& e,
                 double height)
{
    const double rx = b.x - a.x, ry = b.y - a.y;
    const double sx = e.x - s.x, sy = e.y - s.y;
    const double r2 = rx * rx + ry * ry;
    const double q2 = sx * sx + sy * sy;
    const double den = Cross(rx, ry, sx, sy);
    if (std::abs(den) <= EPS * std::sqrt(r2 * q2))
    {
        if (std::abs(Cross(a.x - s.x, a.y - s.y, sx, sy)) > EPS * std::sqrt(q2))
        {
            return false;
        }
        if (r2 <= EPS * EPS)
        {
            const double u = ((a.x - s.x) * sx + (a.y - s.y) * sy) / q2;
            if (u < -EPS || u > 1 + EPS) return false;
            return std::max(a.z, b.z) >= -EPS && std::min(a.z, b.z) <= height + EPS;
        }
        double t0 = ((s.x - a.x) * rx + (s.y - a.y) * ry) / r2;
        double t1 = ((e.x - a.x) * rx + (e.y - a.y) * ry) / r2;
        const double lo = std::max(0.0, std::min(t0, t1));
        const double hi = std::min(1.0, std::max(t0, t1));
        if (lo > hi + EPS) return false;
        const double z0 = a.z + lo * (b.z - a.z);
        const double z1 = a.z + hi * (b.z - a.z);
        return std::max(z0, z1) >= -EPS && std::min(z0, z1) <= height + EPS;
    }
    const double t = Cross(s.x - a.x, s.y - a.y, sx, sy) / den;
    const double u = Cross(s.x - a.x, s.y - a.y, rx, ry) / den;
    const double z = a.z + t * (b.z - a.z);
    return t >= -EPS && t <= 1 + EPS && u >= -EPS && u <= 1 + EPS &&
           z >= -EPS && z <= height + EPS;
}

bool Crosses(const Vector& a, const Vector& b, const ObstaclePropagationLossModel::Obstacle& o)
{
    if (!o.rectangle) return WallCrosses(a, b, o.start, o.end, o.height);
    const double xmin = std::min(o.start.x, o.end.x);
    const double xmax = std::max(o.start.x, o.end.x);
    const double ymin = std::min(o.start.y, o.end.y);
    const double ymax = std::max(o.start.y, o.end.y);
    double lo = 0.0, hi = 1.0;
    auto clip = [&](double p, double q) {
        if (std::abs(p) <= EPS) return q >= -EPS;
        const double t = q / p;
        if (p < 0) lo = std::max(lo, t);
        else hi = std::min(hi, t);
        return lo <= hi + EPS;
    };
    if (!clip(-(b.x - a.x), a.x - xmin) || !clip(b.x - a.x, xmax - a.x) ||
        !clip(-(b.y - a.y), a.y - ymin) || !clip(b.y - a.y, ymax - a.y)) return false;
    const double z0 = a.z + lo * (b.z - a.z);
    const double z1 = a.z + hi * (b.z - a.z);
    return std::max(z0, z1) >= -EPS && std::min(z0, z1) <= o.height + EPS;
}
}

NS_OBJECT_ENSURE_REGISTERED(ObstaclePropagationLossModel);

TypeId
ObstaclePropagationLossModel::GetTypeId()
{
    static TypeId tid = TypeId("ns3::ObstaclePropagationLossModel")
                            .SetParent<PropagationLossModel>()
                            .SetGroupName("Propagation")
                            .AddConstructor<ObstaclePropagationLossModel>();
    return tid;
}

void
ObstaclePropagationLossModel::SetBaseModel(Ptr<PropagationLossModel> model)
{
    if (!model || model == this)
    {
        throw std::invalid_argument("base model must be non-null and cannot wrap itself");
    }
    m_base = model;
}

void
ObstaclePropagationLossModel::AddObstacle(bool rectangle,
                                           Vector start,
                                           Vector end,
                                           double heightM,
                                           bool blocks,
                                           double attenuationDb,
                                           double reflectionLossDb)
{
    const double width = std::abs(end.x - start.x);
    const double depth = std::abs(end.y - start.y);
    if (m_obstacles.size() >= 32 || !Finite(start) || !Finite(end) ||
        (rectangle ? (width <= EPS || depth <= EPS)
                   : (std::hypot(width, depth) <= EPS)) ||
        !std::isfinite(heightM) || heightM <= 0 || heightM > 10000 ||
        !std::isfinite(attenuationDb) || attenuationDb < 0 || attenuationDb > 300 ||
        !std::isfinite(reflectionLossDb) ||
        (reflectionLossDb < 0 && reflectionLossDb != -1) || reflectionLossDb > 300 ||
        (!blocks && reflectionLossDb >= 0 &&
         std::pow(10.0, -attenuationDb / 10.0) +
             std::pow(10.0, -reflectionLossDb / 10.0) > 1.0 + 1e-12))
    {
        throw std::invalid_argument("invalid obstacle geometry or material");
    }
    m_obstacles.push_back(
        {rectangle, start, end, heightM, blocks, attenuationDb, reflectionLossDb});
}

std::vector<ReflectionPath>
ObstaclePropagationLossModel::GetPaths(double power,
                                         Ptr<MobilityModel> tx,
                                         Ptr<MobilityModel> rx) const
{
    if (!m_base) throw std::logic_error("base propagation model is not set");
    std::vector<ReflectionPath> paths;
    if (!tx || !rx || !std::isfinite(power))
    {
        throw std::invalid_argument("finite power and non-null mobility models are required");
    }
    const Vector a = tx->GetPosition();
    const Vector b = rx->GetPosition();
    if (!Finite(a) || !Finite(b))
    {
        throw std::invalid_argument("node positions must be finite");
    }

    auto addPath = [&](const Vector& from,
                       const Vector& to,
                       int reflectedIndex,
                       const Vector& bounce,
                       double reflectionLoss,
                       double firstLegLoss,
                       double secondLegLoss) {
        const double distance = reflectedIndex < 0
                                    ? Distance(from, to)
                                    : Distance(from, bounce) + Distance(bounce, to);
        auto source = CreateObject<ConstantPositionMobilityModel>();
        auto destination = CreateObject<ConstantPositionMobilityModel>();
        source->SetPosition(Vector(0, 0, 0));
        destination->SetPosition(Vector(distance, 0, 0));
        const double transmissionLoss = firstLegLoss + secondLegLoss;
        const double received = m_base->CalcRxPower(power, source, destination) -
                                transmissionLoss - reflectionLoss;
        if (!std::isfinite(distance) || !std::isfinite(received))
        {
            throw std::overflow_error("nonfinite path calculation; check coordinates and model parameters");
        }
        paths.push_back({reflectedIndex < 0 ? "direct" : "reflected",
                         reflectedIndex,
                         distance,
                         received,
                         reflectionLoss,
                         transmissionLoss,
                         bounce});
    };

    auto legLoss = [&](const Vector& from, const Vector& to, int reflector, double& loss) {
        loss = 0;
        for (size_t i = 0; i < m_obstacles.size(); ++i)
        {
            if (static_cast<int>(i) == reflector || !Crosses(from, to, m_obstacles[i])) continue;
            if (m_obstacles[i].blocks) return false;
            loss += m_obstacles[i].attenuation;
        }
        return true;
    };

    double directLoss = 0;
    if (legLoss(a, b, -1, directLoss)) addPath(a, b, -1, Vector(), 0, directLoss, 0);

    // ponytail: O(N²) obstacle/path checks per sample; use spatial indexing if scene size grows.
    for (size_t index = 0; index < m_obstacles.size(); ++index)
    {
        const auto& obstacle = m_obstacles[index];
        if (obstacle.reflection < 0) continue;
        std::vector<std::pair<Vector, Vector>> faces;
        if (!obstacle.rectangle)
        {
            faces.emplace_back(obstacle.start, obstacle.end);
        }
        else
        {
            const double xmin = std::min(obstacle.start.x, obstacle.end.x);
            const double xmax = std::max(obstacle.start.x, obstacle.end.x);
            const double ymin = std::min(obstacle.start.y, obstacle.end.y);
            const double ymax = std::max(obstacle.start.y, obstacle.end.y);
            faces.emplace_back(Vector(xmin, ymin, 0), Vector(xmax, ymin, 0));
            faces.emplace_back(Vector(xmax, ymin, 0), Vector(xmax, ymax, 0));
            faces.emplace_back(Vector(xmax, ymax, 0), Vector(xmin, ymax, 0));
            faces.emplace_back(Vector(xmin, ymax, 0), Vector(xmin, ymin, 0));
        }

        for (const auto& face : faces)
        {
            const double sx = face.second.x - face.first.x;
            const double sy = face.second.y - face.first.y;
            const double lengthSquared = sx * sx + sy * sy;
            const double nx = -sy, ny = sx;
            const double sideA = (a.x - face.first.x) * nx + (a.y - face.first.y) * ny;
            const double sideB = (b.x - face.first.x) * nx + (b.y - face.first.y) * ny;
            if (obstacle.rectangle ? (sideA >= -EPS || sideB >= -EPS)
                                   : (sideA * sideB <= EPS)) continue;

            const double projection = sideA / lengthSquared;
            const Vector image(a.x - 2 * projection * nx,
                               a.y - 2 * projection * ny,
                               a.z);
            const double rayX = b.x - image.x;
            const double rayY = b.y - image.y;
            const double denominator = Cross(rayX, rayY, sx, sy);
            if (std::abs(denominator) <= EPS) continue;
            const double t = Cross(face.first.x - image.x,
                                   face.first.y - image.y,
                                   sx,
                                   sy) / denominator;
            const double u = Cross(face.first.x - image.x,
                                   face.first.y - image.y,
                                   rayX,
                                   rayY) / denominator;
            if (t <= EPS || t >= 1 - EPS || u <= EPS || u >= 1 - EPS) continue;
            const Vector bounce(image.x + t * rayX,
                                image.y + t * rayY,
                                a.z + t * (b.z - a.z));
            if (bounce.z < 0 || bounce.z > obstacle.height) continue;

            double firstLoss = 0, secondLoss = 0;
            if (legLoss(a, bounce, static_cast<int>(index), firstLoss) &&
                legLoss(bounce, b, static_cast<int>(index), secondLoss))
            {
                addPath(a, b, static_cast<int>(index), bounce, obstacle.reflection,
                        firstLoss, secondLoss);
            }
        }
    }
    return paths;
}

double
ObstaclePropagationLossModel::DoCalcRxPower(double power,
                                             Ptr<MobilityModel> tx,
                                             Ptr<MobilityModel> rx) const
{
    const auto paths = GetPaths(power, tx, rx);
    if (paths.empty()) return -INFINITY;
    double maximum = -INFINITY;
    for (const auto& path : paths) maximum = std::max(maximum, path.rxPowerDbm);
    double sum = 0;
    for (const auto& path : paths)
    {
        sum += std::pow(10.0, (path.rxPowerDbm - maximum) / 10.0);
    }
    return maximum + 10 * std::log10(sum);
}

int64_t
ObstaclePropagationLossModel::DoAssignStreams(int64_t)
{
    return 0;
}

} // namespace ns3
