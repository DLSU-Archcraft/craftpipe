-- craftpipe_java_rules: make Mineclonia's redstone follow Minecraft Java
-- in the places where craftpipe's parity tests measured a difference.
--
--  1. Dust connects only to what Java connects it to.
--  2. An unconnected dust is a cross, unless a player made it a dot.
--  3. A comparator reading a container through a solid block outputs 15
--     when that block is powered at 15.
--  4. A redstone lamp lights in the tick it is powered.
--
-- Everything here overrides node definitions or wraps mcl_redstone
-- functions at load time; no Mineclonia file is changed. The parity
-- tests in the craftpipe repository run with this mod loaded and compare
-- against a real Minecraft server, so a Mineclonia update that breaks an
-- assumption made here shows up there.

local DOT = "mcl_redstone:redstone"
local CROSS = "mcl_redstone:wire_0f"
local DOT_KEY = "java_dot"      -- set on a dot a player (or a converted build) chose

local function require_present(what, value)
	if value == nil then
		error("craftpipe_java_rules: this Mineclonia version has no " .. what
			.. "; the mod needs updating before it can be used with it")
	end
end

require_present("mcl_redstone._connect_with_wires", mcl_redstone._connect_with_wires)
require_present("mcl_redstone._update_opaque_connections", mcl_redstone._update_opaque_connections)
require_present("mcl_redstone.get_power", mcl_redstone.get_power)
require_present("mcl_redstone.swap_node", mcl_redstone.swap_node)
require_present("node " .. DOT, core.registered_nodes[DOT])
require_present("node " .. CROSS, core.registered_nodes[CROSS])

local function is_wire(name)
	return core.get_item_group(name, "redstone_wire") ~= 0
end

------------------------------------------------------------------------
-- 1. What dust connects to
------------------------------------------------------------------------

-- Java connects dust to other dust, to repeaters (front and back), to an
-- observer's output and to signal sources. These are the Mineclonia
-- nodes that correspond; every other node loses its dust connection.
local JAVA_CONNECTS = {
	"^mcl_lever:", "^mcl_buttons:", "^mcl_redstone_torch:", "^mcl_pressureplates:",
	"^mcl_comparators:", "^mcl_repeaters:", "^mcl_observers:", "^mcl_target:",
	"^mcl_daylight_detector:", "^mcl_lectern:", "^mcl_chests:trapped_chest",
	"^mcl_minecarts:detector_rail", "^mcl_lightning_rods:", "^mcl_tripwire",
	"^mcl_jukebox:", "^mcl_sculk:.*sensor",
}

local function java_connects(name)
	for _, pattern in ipairs(JAVA_CONNECTS) do
		if name:find(pattern) then
			return true
		end
	end
	return false
end

-- Runs after every mod has registered its nodes. Dust looks the
-- connection up in the node definition each time it re-shapes, so
-- changing the definitions here is enough.
core.register_on_mods_loaded(function()
	local removed = {}
	for name, def in pairs(core.registered_nodes) do
		local redstone = def._mcl_redstone
		if redstone and redstone.connects_to and not java_connects(name) then
			local copy = table.copy(redstone)
			copy.connects_to = nil
			core.override_item(name, {_mcl_redstone = copy})
			removed[#removed + 1] = name
		end
	end
	table.sort(removed)
	core.log("action", "[craftpipe_java_rules] dust no longer connects to "
		.. #removed .. " node types: " .. table.concat(removed, ", "))
end)

------------------------------------------------------------------------
-- 2. Unconnected dust is a cross
------------------------------------------------------------------------

-- Mineclonia re-shapes dust in a private function that turns an
-- unconnected dust into a dot. Every call to it goes through one of the
-- functions wrapped below; after each, dots that nobody asked for are
-- turned into crosses.
local function fix(pos)
	local node = core.get_node(pos)
	if node.name == DOT then
		if core.get_meta(pos):get_string(DOT_KEY) ~= "1" then
			mcl_redstone.swap_node(pos, {name = CROSS, param2 = node.param2})
		end
	elseif node.name ~= CROSS and is_wire(node.name) then
		-- Connected again: like Java, it forgets it was ever a dot.
		local meta = core.get_meta(pos)
		if meta:get_string(DOT_KEY) ~= "" then
			meta:set_string(DOT_KEY, "")
		end
	end
end

local AROUND_WIRE = {}
for _, d in ipairs({{0, 0}, {1, 0}, {-1, 0}, {0, 1}, {0, -1}}) do
	for dy = -1, 1 do
		if not (dy ~= 0 and d[1] == 0 and d[2] == 0) then
			AROUND_WIRE[#AROUND_WIRE + 1] = vector.new(d[1], dy, d[2])
		end
	end
end
local AROUND_NODE = {
	vector.new(1, 0, 0), vector.new(-1, 0, 0), vector.new(0, 0, 1), vector.new(0, 0, -1),
	vector.new(0, -1, 0),
}

local function fix_around(pos, offsets)
	for _, offset in ipairs(offsets) do
		fix(vector.add(pos, offset))
	end
end

local connect_with_wires = mcl_redstone._connect_with_wires
function mcl_redstone._connect_with_wires(pos)
	connect_with_wires(pos)
	fix_around(pos, AROUND_NODE)
end

local update_opaque_connections = mcl_redstone._update_opaque_connections
function mcl_redstone._update_opaque_connections(pos)
	update_opaque_connections(pos)
	fix_around(pos, AROUND_NODE)
end

for name, def in pairs(core.registered_nodes) do
	if is_wire(name) then
		local on_construct, after_destruct, on_rightclick =
			def.on_construct, def.after_destruct, def.on_rightclick
		local override = {
			on_construct = function(pos)
				if on_construct then
					on_construct(pos)
				end
				fix_around(pos, AROUND_WIRE)
			end,
			after_destruct = function(pos, oldnode)
				if after_destruct then
					after_destruct(pos, oldnode)
				end
				fix_around(pos, AROUND_WIRE)
			end,
		}
		if on_rightclick then
			-- Right-click toggles a lone dust between cross and dot.
			override.on_rightclick = function(pos, node, ...)
				local was_dot = core.get_node(pos).name == DOT
				local result = on_rightclick(pos, node, ...)
				local meta = core.get_meta(pos)
				if not was_dot and core.get_node(pos).name == DOT then
					meta:set_string(DOT_KEY, "1")          -- the player asked for a dot
				else
					meta:set_string(DOT_KEY, "")
				end
				fix_around(pos, AROUND_WIRE)
				return result
			end
		end
		core.override_item(name, override)
	end
end

------------------------------------------------------------------------
-- 3. Comparator through a block powered at 15
------------------------------------------------------------------------

-- Nodes a comparator measures directly. When one of these is right behind
-- the comparator, Java reads it whatever power it receives, as Mineclonia
-- already does.
local function is_measured_directly(name)
	return core.get_item_group(name, "container") ~= 0
		or name:find("^mcl_lectern:lectern_with_book") ~= nil
		or name:find("^mcl_jukebox:") ~= nil
		or name:find("^mcl_target:") ~= nil
		or name:find("^mcl_books:chiseled_bookshelf") ~= nil
		or name:find("^mcl_cauldrons:") ~= nil
		or name:find("^mcl_composters:") ~= nil
		or name:find("^mcl_cake:") ~= nil
		or name:find("^mcl_beds:respawn_anchor") ~= nil
		or name:find("^mcl_brewing:") ~= nil
		or name:find("^mcl_portals:end_portal_frame") ~= nil
		or name:find("^mcl_copper:bulb") ~= nil
end

for _, mode in ipairs({"comp", "sub"}) do
	for _, state in ipairs({"on", "off"}) do
		local name = "mcl_comparators:comparator_" .. state .. "_" .. mode
		local def = core.registered_nodes[name]
		require_present("node " .. name, def and def._mcl_redstone and def._mcl_redstone.update)
		local update = def._mcl_redstone.update
		local redstone = table.copy(def._mcl_redstone)
		redstone.update = function(pos, node)
			local back = -core.fourdir_to_dir(node.param2)
			local behind = core.get_node(vector.add(pos, back)).name
			if mcl_redstone._solid_opaque_tab[behind] and not is_measured_directly(behind)
					and mcl_redstone.get_power(pos, back) >= 15 then
				-- Java: a solid block powered at 15 wins over a container
				-- behind it.
				local left = core.fourdir_to_dir((node.param2 - 1) % 4)
				local right = core.fourdir_to_dir((node.param2 + 1) % 4)
				local side = math.max(mcl_redstone.get_power(pos, left, "direct"),
					mcl_redstone.get_power(pos, right, "direct"))
				local output
				if mode == "comp" then
					output = 15 >= side and 15 or 0
				else
					output = math.max(15 - side, 0)
				end
				return {
					name = "mcl_comparators:comparator_" .. (output > 0 and "on" or "off") .. "_" .. mode,
					param2 = 4 * output + node.param2 % 4,
				}
			end
			return update(pos, node)
		end
		core.override_item(name, {_mcl_redstone = redstone})
	end
end

------------------------------------------------------------------------
-- 4. Lamps light at once
------------------------------------------------------------------------

do
	local name = "mcl_redstone_lamp:lamp_off"
	local def = core.registered_nodes[name]
	require_present("node " .. name, def and def._mcl_redstone and def._mcl_redstone.update)
	local update = def._mcl_redstone.update
	local redstone = table.copy(def._mcl_redstone)
	redstone.update = function(pos, node)
		local result = update(pos, node)
		if result and result.name == "mcl_redstone_lamp:lamp_on" then
			-- Mineclonia would schedule this for the next tick. A lamp
			-- powers nothing, so it is safe to light it right away.
			mcl_redstone.swap_node(pos, {name = result.name, param2 = node.param2})
			return nil
		end
		return result
	end
	core.override_item(name, {_mcl_redstone = redstone})
end
