-- craftpipe_loader: place a schematic produced by `craftpipe convert`.
--
-- A plain schematic paste skips every node's on_construct, which leaves
-- containers without inventories and redstone uninitialised. This mod
-- places <world>/schems/<name>.mts, runs the skipped setup, restores the
-- dust shapes Minecraft saved, and applies <name>.craftpipe.json
-- (container contents, lectern pages).
--
-- Both files may come from someone else (a student submission), so they
-- are treated as untrusted:
--   * the manifest is parsed as JSON and never executed;
--   * the schematic may only contain nodes the converter can produce
--     (allowed_nodes.lua), so it cannot carry e.g. a command block;
--   * the manifest may only fill inventories of container nodes and set
--     the page of a lectern; no other metadata can be written.

craftpipe = {}

local MANIFEST_FORMAT = 1
local ALLOWED_NODES = dofile(core.get_modpath(core.get_current_modname()) .. "/allowed_nodes.lua")
local ALLOWED_LISTS = {main = true, src = true, fuel = true, dst = true}
local LECTERN = "mcl_lectern:lectern_with_book"
local DOT = "mcl_redstone:redstone"

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
local function load_manifest(name, mts_size, mts_sha1)
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
	if manifest.mts_sha1 ~= mts_sha1 or not is_pos_list(size) or size[1] ~= mts_size.x
			or size[2] ~= mts_size.y or size[3] ~= mts_size.z then
		return nil, "manifest does not belong to this schematic; copy the .mts and the "
			.. ".craftpipe.json from the same conversion"
	end
	for _, key in ipairs({"containers", "meta"}) do
		local list = manifest[key]
		if list ~= nil and type(list) ~= "table" then
			return nil, "manifest field '" .. key .. "' is malformed"
		end
		for i = 1, #(list or {}) do
			local entry = list[i]
			if type(entry) ~= "table" or not is_pos_list(entry.pos)
					or not inside(entry.pos, size) then
				return nil, "manifest refers to a position outside the schematic"
			end
		end
	end
	return manifest
end

-- Luanti caches schematics by file name until the server restarts, so a
-- re-converted build would silently be replaced by the stale copy. Place
-- from a copy named after the file's contents instead.
local function content_addressed_copy(data, sha1)
	local dir = schems_dir() .. "craftpipe_cache"
	core.mkdir(dir)
	local path = dir .. "/" .. sha1 .. ".mts"
	if read_file(path) ~= data then
		if not core.safe_file_write(path, data) then
			return nil
		end
	end
	return path
end

local function wire_flags(name)
	if name == DOT then
		return 0
	end
	local hex = name:match("^mcl_redstone:wire_(%x%x)$")
	return hex and tonumber(hex, 16) or nil
end

local function wire_name(flags)
	return flags == 0 and DOT or string.format("mcl_redstone:wire_%02x", flags)
end

-- Checks every node name and collects the dust shapes saved by Minecraft.
-- Returns list of {x, y, z, mask} (schematic-relative), or nil and a message.
local function inspect_schematic(schematic)
	local size = schematic.size
	local verdict = {}        -- name -> true (ok) / false (refused)
	local refused, n_refused = {}, 0
	local wires = {}
	local i = 1
	for z = 0, size.z - 1 do
		for y = 0, size.y - 1 do
			for x = 0, size.x - 1 do
				local name = schematic.data[i].name
				local ok = verdict[name]
				if ok == nil then
					ok = ALLOWED_NODES[name] == true and
						(name == "air" or core.registered_nodes[name] ~= nil)
					verdict[name] = ok
					if not ok and n_refused < 5 then
						n_refused = n_refused + 1
						refused[n_refused] = name
					end
				end
				if ok then
					local flags = wire_flags(name)
					if flags then
						wires[#wires + 1] = {x, y, z, flags % 16}
					end
				end
				i = i + 1
			end
		end
	end
	if n_refused > 0 then
		return nil, "schematic contains nodes craftpipe does not produce or this game does not "
			.. "have (" .. table.concat(refused, ", ") .. "); refusing to place it"
	end
	return wires
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

-- Mineclonia re-shapes dust in on_construct by its own rules, which differ
-- from Java's (dust connects to lamps and droppers; an unconnected dust
-- becomes a dot). Keep Mineclonia's "climbs onto the next block" bits, but
-- put the four horizontal connections back to what Minecraft saved.
local function restore_dust_shapes(origin, wires)
	for _, w in ipairs(wires) do
		local pos = vector.new(origin.x + w[1], origin.y + w[2], origin.z + w[3])
		local node = core.get_node(pos)
		local current = wire_flags(node.name)
		if current then
			local mask = w[4]
			local wanted = wire_name(mask + 16 * bit.band(math.floor(current / 16), mask))
			if wanted ~= node.name and core.registered_nodes[wanted] then
				core.swap_node(pos, {name = wanted, param2 = node.param2})
			end
			-- A dust Minecraft saved as a dot was made a dot on purpose.
			-- The craftpipe_java_rules mod, if loaded, keeps such dots and
			-- turns any other unconnected dust into a cross.
			core.get_meta(pos):set_string("java_dot", wanted == DOT and "1" or "")
		end
	end
end

-- Some Mineclonia containers only set themselves up when a player places
-- them (droppers), or when the game turns a single chest into a double
-- one, so on_construct alone leaves them without an inventory.
local function prepare_inventory(pos, inv, sizes)
	if type(sizes) ~= "table" then
		return
	end
	local missing = false
	for listname in pairs(sizes) do
		if ALLOWED_LISTS[listname] and inv:get_size(listname) == 0 then
			missing = true
		end
	end
	if not missing then
		return
	end
	local def = core.registered_nodes[core.get_node(pos).name]
	if def and def.after_place_node and not def.on_construct then
		pcall(def.after_place_node, pos, nil, ItemStack(""), nil)
	end
	for listname, size in pairs(sizes) do
		size = tonumber(size)
		if ALLOWED_LISTS[listname] and size and size >= 1 and size <= 27
				and inv:get_size(listname) < size then
			inv:set_size(listname, size)
		end
	end
end

-- Returns containers filled, item stacks that could not be placed.
local function apply_containers(origin, manifest)
	local filled, skipped = 0, 0
	local list = manifest.containers or {}
	for e = 1, #list do
		local entry = list[e]
		local pos = world_pos(origin, entry.pos)
		local name = core.get_node(pos).name
		-- Only real containers placed by this schematic get an inventory.
		if ALLOWED_NODES[name] and core.get_item_group(name, "container") ~= 0 then
			local inv = core.get_meta(pos):get_inventory()
			prepare_inventory(pos, inv, entry.sizes)
			for listname, stacks in pairs(type(entry.lists) == "table" and entry.lists or {}) do
				if ALLOWED_LISTS[listname] and type(stacks) == "table" then
					local size = inv:get_size(listname)
					for s = 1, #stacks do
						local stack = stacks[s]
						local slot = type(stack) == "table" and tonumber(stack.slot)
						local n = type(stack) == "table" and tonumber(stack.count)
						local item = type(stack) == "table" and stack.name
						if slot and n and type(item) == "string" and slot >= 1 and slot <= size
								and slot == math.floor(slot) and n >= 1
								and core.registered_items[item] then
							inv:set_stack(listname, slot, ItemStack({name = item, count = n}))
						else
							skipped = skipped + 1
						end
					end
				end
			end
			filled = filled + 1
			if mcl_redstone.update_comparators then
				mcl_redstone.update_comparators(pos)
			end
		end
	end
	return filled, skipped
end

-- The only metadata a manifest may set: which page a lectern's book is on.
local function apply_meta(origin, manifest)
	local list = manifest.meta or {}
	for e = 1, #list do
		local entry = list[e]
		local pos = world_pos(origin, entry.pos)
		local fields = entry.fields
		if core.get_node(pos).name == LECTERN and type(fields) == "table" then
			local pages, page = tonumber(fields.pages), tonumber(fields.page)
			if pages and page and pages >= 1 and pages <= 1000 and page >= 1 and page <= pages then
				local meta = core.get_meta(pos)
				meta:set_string("pages", tostring(math.floor(pages)))
				meta:set_string("page", tostring(math.floor(page)))
				if mcl_redstone.update_comparators then
					mcl_redstone.update_comparators(pos)
				end
			end
		end
	end
end

local function valid_name(name)
	return type(name) == "string" and name:match("^[%w_%-]+$") ~= nil
end

-- Reads and checks both files. Returns {path, schematic, manifest, wires}
-- or nil and a message.
local function prepare(name)
	if not valid_name(name) then
		return nil, "invalid schematic name (use letters, digits, _ and - only)"
	end
	local data = read_file(schems_dir() .. name .. ".mts")
	if not data then
		return nil, "cannot read " .. name .. ".mts from the world's schems folder"
	end
	local sha1 = core.sha1(data)
	local path = content_addressed_copy(data, sha1)
	local schematic = path and core.read_schematic(path, {})
	if not schematic then
		return nil, name .. ".mts is not a schematic this server can read"
	end
	local manifest, err = load_manifest(name, schematic.size, sha1)
	if not manifest then
		return nil, err
	end
	local wires, refused = inspect_schematic(schematic)
	if not wires then
		return nil, refused
	end
	return {path = path, schematic = schematic, manifest = manifest, wires = wires}
end

local function place_prepared(pos, name, job)
	local size = job.schematic.size
	local p1 = vector.round(pos)
	local p2 = vector.add(p1, vector.subtract(size, 1))
	if core.place_schematic(p1, job.path, "0", nil, true) == nil then
		return false, "the engine refused to place the schematic"
	end
	local nodes = construct_nodes(p1, p2)
	restore_dust_shapes(p1, job.wires)
	local containers, skipped = apply_containers(p1, job.manifest)
	apply_meta(p1, job.manifest)

	local message = string.format("placed %s: %dx%dx%d, %d nodes set up, %d container(s) filled",
		name, size.x, size.y, size.z, nodes, containers)
	if skipped > 0 then
		message = message .. ". WARNING: " .. skipped .. " item stack(s) could not be placed "
			.. "(unknown item or slot); container signals will differ from the original"
	end
	if job.manifest.complete == false then
		local n = 0
		for _ in pairs(type(job.manifest.substituted) == "table" and job.manifest.substituted or {}) do
			n = n + 1
		end
		message = "WARNING: not gradeable. " .. n .. " kind(s) of block had no Mineclonia "
			.. "equivalent and were replaced with placeholders; the circuit may not behave "
			.. "like the original. " .. message
	end
	return true, {nodes = nodes, containers = containers, skipped_stacks = skipped,
		complete = job.manifest.complete ~= false, message = message}
end

--- Place schematic `name` with its minimum corner at `pos`.
-- The target area must already be generated (see craftpipe.place_async).
-- Returns true and a stats table {nodes, containers, skipped_stacks,
-- complete, message}, or false and a message. Nothing is placed on failure.
function craftpipe.place(pos, name)
	local job, err = prepare(name)
	if not job then
		return false, err
	end
	return place_prepared(pos, name, job)
end

--- Generate the target area if needed, then place. `callback(ok, result)`
-- receives what craftpipe.place returns.
function craftpipe.place_async(pos, name, callback)
	local job, err = prepare(name)
	if not job then
		callback(false, err)
		return
	end
	local p1 = vector.round(pos)
	local p2 = vector.add(p1, vector.subtract(job.schematic.size, 1))
	local done = false
	core.emerge_area(vector.subtract(p1, 1), vector.add(p2, 1), function(_, action, remaining)
		if done then
			return
		end
		if action == core.EMERGE_CANCELLED or action == core.EMERGE_ERRORED then
			done = true
			callback(false, "the area could not be generated; nothing was placed")
		elseif remaining == 0 then
			done = true
			callback(place_prepared(p1, name, job))
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
