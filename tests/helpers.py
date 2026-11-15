from craftpipe.grid import BlockState, VoxelGrid


def grids_equal(a: VoxelGrid, b: VoxelGrid) -> bool:
    return (a.size == b.size
            and all(sa == sb for (_, sa), (_, sb) in zip(a.cells(), b.cells()))
            and a.block_entities == b.block_entities)


def sample_grid(size=(3, 2, 4), n_states=5) -> VoxelGrid:
    """A grid whose cells cycle through n_states distinct states (plus air)."""
    g = VoxelGrid(size)
    states = [BlockState("minecraft:stone", (("n", str(i)),)) for i in range(n_states)]
    i = 0
    for (x, y, z), _ in list(g.cells()):
        if i % (n_states + 1) != n_states:
            g.set(x, y, z, states[i % (n_states + 1)])
        i += 1
    return g
