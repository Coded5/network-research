package propagationlab;

module CalibratedPathLoss extends inet.physicallayer.wireless.common.pathloss.FreeSpacePathLoss
{
    @class(propagationlab::CalibratedPathLoss);
}

simple PropagationLab
{
    @class(propagationlab::PropagationLab);
}

network PropagationNetwork
{
    submodules:
        pathLoss: CalibratedPathLoss;
        evaluator: PropagationLab;
}
