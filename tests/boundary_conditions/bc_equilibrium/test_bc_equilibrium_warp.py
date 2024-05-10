import pytest
import numpy as np
import warp as wp
import xlb
from xlb.compute_backend import ComputeBackend
from xlb.grid import grid_factory
from xlb.default_config import DefaultConfig


def init_xlb_env(velocity_set):
    xlb.init(
        default_precision_policy=xlb.PrecisionPolicy.FP32FP32,
        default_backend=ComputeBackend.WARP,
        velocity_set=velocity_set,
    )


@pytest.mark.parametrize(
    "dim,velocity_set,grid_shape",
    [
        (2, xlb.velocity_set.D2Q9, (100, 100)),
        (2, xlb.velocity_set.D2Q9, (100, 100)),
        (3, xlb.velocity_set.D3Q19, (50, 50, 50)),
        (3, xlb.velocity_set.D3Q19, (50, 50, 50)),
    ],
)
def test_bc_equilibrium_warp(dim, velocity_set, grid_shape):
    init_xlb_env(velocity_set)
    my_grid = grid_factory(grid_shape)
    velocity_set = DefaultConfig.velocity_set

    missing_mask = my_grid.create_field(
        cardinality=velocity_set.q, dtype=xlb.Precision.BOOL
    )

    boundary_id_field = my_grid.create_field(cardinality=1, dtype=xlb.Precision.UINT8)

    indices_boundary_masker = xlb.operator.boundary_masker.IndicesBoundaryMasker()

    # Make indices for boundary conditions (sphere)
    sphere_radius = grid_shape[0] // 4
    nr = grid_shape[0]
    x = np.arange(nr)
    y = np.arange(nr)
    z = np.arange(nr)
    if dim == 2:
        X, Y = np.meshgrid(x, y)
        indices = np.where((X - nr // 2) ** 2 + (Y - nr // 2) ** 2 < sphere_radius**2)
    else:
        X, Y, Z = np.meshgrid(x, y, z)
        indices = np.where(
            (X - nr // 2) ** 2 + (Y - nr // 2) ** 2 + (Z - nr // 2) ** 2
            < sphere_radius**2
        )

    indices = wp.array(indices, dtype=wp.int32)

    equilibrium = xlb.operator.equilibrium.QuadraticEquilibrium()

    equilibrium_bc = xlb.operator.boundary_condition.EquilibriumBC(
        rho=1.0,
        u=(0.0, 0.0, 0.0) if dim == 3 else (0.0, 0.0),
        equilibrium_operator=equilibrium,
    )

    boundary_id_field, missing_mask = indices_boundary_masker(
        indices, equilibrium_bc.id, boundary_id_field, missing_mask, start_index=None
    )

    f = my_grid.create_field(cardinality=velocity_set.q, dtype=xlb.Precision.FP32)
    f_pre = my_grid.create_field(cardinality=velocity_set.q, dtype=xlb.Precision.FP32)
    f_post = my_grid.create_field(
        cardinality=velocity_set.q, dtype=xlb.Precision.FP32, fill_value=2.0
    )  # Arbitrary value so that we can check if the values are changed outside the boundary

    f = equilibrium_bc(f_pre, f_post, boundary_id_field, missing_mask, f)

    f = f.numpy()
    f_post = f_post.numpy()
    indices = indices.numpy()

    assert f.shape == (velocity_set.q,) + grid_shape

    # Assert that the values are correct in the indices of the sphere
    weights = velocity_set.w
    for i, weight in enumerate(weights):
        if dim == 2:
            assert np.allclose(
                f[i, indices[0], indices[1]], weight
            ), f"Direction {i} in f does not match the expected weight"
        else:
            assert np.allclose(
                f[i, indices[0], indices[1], indices[2]], weight
            ), f"Direction {i} in f does not match the expected weight"

    # Make sure that everywhere else the values are the same as f_post. Note that indices are just int values
    mask_outside = np.ones(grid_shape, dtype=bool)
    mask_outside[indices] = False  # Mark boundary as false
    if dim == 2:
        for i in range(velocity_set.q):
            assert np.allclose(f[i, mask_outside], f_post[i, mask_outside])
    else:
        for i in range(velocity_set.q):
            assert np.allclose(f[i, mask_outside], f_post[i, mask_outside])


if __name__ == "__main__":
    pytest.main()
