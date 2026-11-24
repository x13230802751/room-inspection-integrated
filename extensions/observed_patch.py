"""Prefer a sufficiently supported patch near the centre of the measured wall points."""
from wall_rms import supported_patch


def select(xyz, wall, floor, boundary, size):
    return supported_patch(xyz, wall, floor, boundary, size, observed_center=True)
