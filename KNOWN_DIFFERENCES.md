# Known differences (scratch, folded into README in Task 10)

- Wooden buttons stay pressed 10 redstone ticks in Mineclonia (Minecraft Java: 15). Stone buttons: 10 in both. Source: mcl_buttons/init.lua push_duration.
- Comparator reading a container through an opaque block: Mineclonia follows Bedrock; Java's exception when the block is powered at 15 is not implemented. Source: comment in mcl_comparators/init.lua.
- Stored state: RS torch latch and locked-repeater latch both kept their bit through conversion + load (tests/engine/test_logic.py::test_stored_state_survives_load).
- Slab towers: signal goes up top-slab towers and not down, same as Java (test_logic slab_up / slab_down).
- Timing: Mineclonia's redstone tick defaults to 0.1 s (same as a Java redstone tick); torch and 1-tick repeater delays are one tick each. 4-bit ripple adder (36 NAND columns) settles in <= 48 redstone ticks (tests/engine/settle_time.json).
- Mineclonia limits redstone work per server step (mcl_redstone_time_budget, default 20% of a tick); a large circuit under load runs slower in wall-clock time but keeps tick order.
- Lecterns: page signal is carried (pages/page metadata), but the book's text is not; the lectern shows as holding a book that cannot be read.
- Furnaces are always placed unlit; a furnace holding both fuel and a smeltable input will start smelting in Mineclonia and its signal will drift, as it would in Minecraft.
- Container items with no Mineclonia equivalent are replaced by a filler of the same stack size (cobblestone / snowball / wooden shovel); signals are unchanged.
