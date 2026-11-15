import pytest

from craftpipe.grid import AIR, BlockState, VoxelGrid

P = BlockState.parse


def test_parse_roundtrip():
    s = "minecraft:repeater[delay=2,facing=north]"
    assert str(P(s)) == s
    assert P("minecraft:repeater[facing=north,delay=2]") == P(s)
    assert P(s).get("delay") == "2"
    assert P(s).get("nope", "x") == "x"


def test_parse_adds_namespace_and_plain_name():
    assert P("stone") == BlockState("minecraft:stone")
    assert str(P("stone")) == "minecraft:stone"


def test_with_props():
    assert P("lever[powered=false]").with_props(powered="true") == P("lever[powered=true]")


def test_default_is_air():
    g = VoxelGrid((2, 2, 2))
    assert g.get(1, 1, 1) == AIR


def test_set_get():
    g = VoxelGrid((2, 3, 4))
    g.set(1, 2, 3, P("stone"))
    assert g.get(1, 2, 3) == P("stone")
    assert g.get(0, 2, 3) == AIR
    assert g.counts()[P("stone")] == 1
    assert list(g.positions(P("stone"))) == [(1, 2, 3)]


@pytest.mark.parametrize("pos", [(2, 0, 0), (0, 3, 0), (0, 0, 4), (-1, 0, 0)])
def test_out_of_range_raises(pos):
    g = VoxelGrid((2, 3, 4))
    with pytest.raises(IndexError):
        g.get(*pos)
    with pytest.raises(IndexError):
        g.set(*pos, P("stone"))


def test_mirror_moves_cells():
    g = VoxelGrid((2, 1, 3))
    g.set(0, 0, 0, P("stone"))
    m = g.mirror_z()
    assert m.get(0, 0, 2) == P("stone")
    assert m.get(0, 0, 0) == AIR


def mirrored(state: str) -> str:
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P(state))
    return str(g.mirror_z().get(0, 0, 0))


def test_mirror_facing():
    assert mirrored("repeater[facing=north]") == "minecraft:repeater[facing=south]"
    assert mirrored("repeater[facing=south]") == "minecraft:repeater[facing=north]"
    assert mirrored("repeater[facing=east]") == "minecraft:repeater[facing=east]"
    assert mirrored("dropper[facing=up]") == "minecraft:dropper[facing=up]"


def test_mirror_dust_sides():
    assert mirrored("redstone_wire[north=side,south=none,east=up,west=none]") == \
        "minecraft:redstone_wire[east=up,north=none,south=side,west=none]"


def test_mirror_chest_handedness():
    assert mirrored("chest[facing=east,type=left]") == "minecraft:chest[facing=east,type=right]"
    assert mirrored("chest[facing=east,type=single]") == "minecraft:chest[facing=east,type=single]"


def test_mirror_stairs_and_hinge():
    assert mirrored("oak_stairs[shape=inner_left]") == "minecraft:oak_stairs[shape=inner_right]"
    assert mirrored("oak_door[hinge=left]") == "minecraft:oak_door[hinge=right]"
    assert mirrored("oak_log[axis=z]") == "minecraft:oak_log[axis=z]"


def test_mirror_twice_is_identity():
    g = VoxelGrid((2, 2, 3))
    g.set(0, 0, 0, P("repeater[facing=north]"))
    g.set(1, 0, 1, P("redstone_wire[north=side,south=none]"))
    g.set(1, 1, 2, P("chest[facing=west,type=left]"))
    g.block_entities[(1, 1, 2)] = {"id": "minecraft:chest"}
    once = g.mirror_z()
    assert (1, 1, 0) in once.block_entities
    twice = once.mirror_z()
    assert twice.size == g.size
    assert all(twice.get(x, y, z) == g.get(x, y, z)
               for x in range(2) for y in range(2) for z in range(3))
    assert twice.block_entities == g.block_entities
