-- craftpipe_loader: place a schematic produced by `craftpipe convert`.
--
-- A plain schematic paste skips every node's on_construct, which leaves
-- redstone dust unconnected and containers without inventories. This mod
-- places <world>/schems/<name>.mts, runs the skipped setup, and then
-- applies <name>.craftpipe.json (container contents and node metadata).
-- The manifest is parsed as JSON; nothing from it is ever executed.

craftpipe = {}

local MANIFEST_FORMAT = 1

local function schems_dir()
	return core.get_worldpath() .. "/schems/"
end

local function read_file(path)
	local f = io.open(path, "rb")
	if not f then
		return nil
	end
	local data = f:read("*a")
	f:close()
	return data
end

local function is_pos_list(v)
	return type(v) == "table" and type(v[1]) == "number" and type(v[2]) == "number"
		and type(v[3]) == "number"
end

local function inside(p, size)
	for i = 1, 3 do
		if p[i] ~= math.floor(p[i]) or p[i] < 0 or p[i] >= size[i] then
			return false
		end
	end
	return true
end

-- Returns manifest, or nil and a message.
local function load_manifest(name, mts_size)
	local text = read_file(schems_dir() .. name .. ".craftpipe.json")
	if not text then
		return nil, "no manifest " .. name .. ".craftpipe.json next to the schematic; "
			.. "convert the build with craftpipe and copy both files"
	end
	local manifest = core.parse_json(text)
	if type(manifest) ~= "table" then
		return nil, "manifest is not valid JSON"
	end
	if manifest.format ~= MANIFEST_FORMAT then
		return nil, "manifest format " .. tostring(manifest.format) .. " is not supported by this loader"
	end
	local size = manifest.size
	if not is_pos_list(size) or size[1] ~= mts_size.x or size[2] ~= mts_size.y
			or size[3] ~= mts_size.z then
		return nil, "manifest does not belong to this schematic (sizes differ)"
	end
	for _, key in ipairs({"containers", "meta"}) do
		local list = manifest[key]
		if list ~= nil and type(list) ~= "table" then
			return nil, "manifest field '" .. key .. "' is malformed"
		end
		for _, entry in ipairs(list or {}) do
			if type(entry) ~= "table" or not is_pos_list(entry.pos)
					or not inside(entry.pos, size) then
				return nil, "manifest refers to a position outside the schematic"
			end
		end
	end
	return manifest
end

local function world_pos(origin, rel)
	return vector.new(origin.x + rel[1], origin.y + rel[2], origin.z + rel[3])
end

-- Run on_construct for every placed node that defines one, exactly as
-- core.set_node would have. Returns the number of nodes handled.
local function construct_nodes(p1, p2)
	local vm = core.get_voxel_manip(p1, p2)
	local emin, emax = vm:get_emerged_area()
	local area = VoxelArea(emin, emax)
	local data = vm:get_data()
	local construct_for = {}
	local count = 0
	for z = p1.z, p2.z do
		for y = p1.y, p2.y do
			local i = area:index(p1.x, y, z)
			for x = p1.x, p2.x do
				local id = data[i]
				local fn = construct_for[id]
				if fn == nil then
					local def = core.registered_nodes[core.get_name_from_content_id(id)]
					fn = def and def.on_construct or false
					construct_for[id] = fn
				end
				if fn then
					fn(vector.new(x, y, z))
					count = count + 1
				end
				i = i + 1
			end
		end
	end
	return count
end

local function apply_containers(origin, manifest)
	local filled = 0
	for _, entry in ipairs(manifest.containers or {}) do
		local pos = world_pos(origin, entry.pos)
		local inv = core.get_meta(pos):get_inventory()
		for listname, stacks in pairs(type(entry.lists) == "table" and entry.lists or {}) do
			local size = inv:get_size(listname)
			for _, stack in ipairs(type(stacks) == "table" and stacks or {}) do
				local slot, item, n = tonumber(stack.slot), stack.name, tonumber(stack.count)
				if slot and n and type(item) == "string" and slot >= 1 and slot <= size
						and core.registered_items[item] then
					inv:set_stack(listname, slot, ItemStack({name = item, count = n}))
				end
			end
		end
		filled = filled + 1
		if mcl_redstone.update_comparators then
			mcl_redstone.update_comparators(pos)
		end
	end
	return filled
end

local function apply_meta(origin, manifest)
	for _, entry in ipairs(manifest.meta or {}) do
		local meta = core.get_meta(world_pos(origin, entry.pos))
		for key, value in pairs(type(entry.fields) == "table" and entry.fields or {}) do
			if type(key) == "string" and (type(value) == "string" or type(value) == "number") then
				meta:set_string(key, tostring(value))
			end
		end
	end
end

--- Place schematic `name` with its minimum corner at `pos`.
-- The target area must already be generated (see craftpipe.place_async).
-- Returns true and a stats table {nodes, containers, complete, message},
-- or false and a message. Nothing is placed on failure.
function craftpipe.place(pos, name)
	if type(name) ~= "string" or not name:match("^[%w_%-]+$") then
		return false, "invalid schematic name (use letters, digits, _ and - only)"
	end
	local path = schems_dir() .. name .. ".mts"
	local schematic = core.read_schematic(path, {})
	if not schematic then
		return false, "cannot read " .. name .. ".mts from the world's schems folder"
	end
	local manifest, err = load_manifest(name, schematic.size)
	if not manifest then
		return false, err
	end

	local p1 = vector.round(pos)
	local p2 = vector.add(p1, vector.subtract(schematic.size, 1))
	if core.place_schematic(p1, path, "0", nil, true) == nil then
		return false, "the engine refused to place the schematic"
	end
	local nodes = construct_nodes(p1, p2)
	local containers = apply_containers(p1, manifest)
	apply_meta(p1, manifest)

	local message = string.format("placed %s: %dx%dx%d, %d nodes set up, %d container(s) filled",
		name, schematic.size.x, schematic.size.y, schematic.size.z, nodes, containers)
	if manifest.complete == false then
		local n = 0
		for _ in pairs(type(manifest.substituted) == "table" and manifest.substituted or {}) do
			n = n + 1
		end
		message = "WARNING: not gradeable. " .. n .. " kind(s) of block had no Mineclonia "
			.. "equivalent and were replaced with placeholders; the circuit may not behave "
			.. "like the original. " .. message
	end
	return true, {nodes = nodes, containers = containers,
		complete = manifest.complete ~= false, message = message}
end

--- Generate the target area if needed, then place. `callback(ok, result)`
-- receives what craftpipe.place returns.
function craftpipe.place_async(pos, name, callback)
	if type(name) ~= "string" or not name:match("^[%w_%-]+$") then
		callback(false, "invalid schematic name (use letters, digits, _ and - only)")
		return
	end
	local schematic = core.read_schematic(schems_dir() .. name .. ".mts", {})
	if not schematic then
		callback(false, "cannot read " .. name .. ".mts from the world's schems folder")
		return
	end
	local p1 = vector.round(pos)
	local p2 = vector.add(p1, vector.subtract(schematic.size, 1))
	core.emerge_area(vector.subtract(p1, 1), vector.add(p2, 1), function(_, _, remaining)
		if remaining == 0 then
			callback(craftpipe.place(p1, name))
		end
	end)
end

core.register_chatcommand("craftpipe_place", {
	params = "<name>",
	description = "Place a craftpipe-converted schematic from the world's schems folder at your position",
	privs = {server = true},
	func = function(player_name, param)
		local player = core.get_player_by_name(player_name)
		if not player then
			return false, "this command needs a player position"
		end
		local name = param:match("^%s*(.-)%s*$")
		craftpipe.place_async(player:get_pos(), name, function(ok, result)
			core.chat_send_player(player_name, ok and result.message or ("craftpipe: " .. result))
		end)
		return true, "craftpipe: placing " .. name .. " ..."
	end,
})
