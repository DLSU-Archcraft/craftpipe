-- Test-only driver. Reads <world>/craftpipe_test/job.json, places the
-- schematic through craftpipe_loader, runs the job's steps with redstone
-- ticks advanced by hand (deterministic, independent of wall-clock time),
-- writes result.json and shuts the server down.

local dir = core.get_worldpath() .. "/craftpipe_test/"

local function read_json(path)
	local f = io.open(path, "rb")
	if not f then
		return nil
	end
	local text = f:read("*a")
	f:close()
	return core.parse_json(text)
end

local result = {steps = {}}

local function finish(err)
	result.error = err
	core.safe_file_write(dir .. "result.json", core.write_json(result))
	core.request_shutdown("craftpipe_test done", false, 0)
end

local function tick(n)
	for _ = 1, n do
		mcl_redstone.tick_step()
	end
end

local function is_on(name)
	return name:sub(-3) == "_on" or name:find("_on_") ~= nil
end

local function run(job)
	local origin = vector.new(job.origin[1], job.origin[2], job.origin[3])
	local function at(rel)
		return vector.new(origin.x + rel[1], origin.y + rel[2], origin.z + rel[3])
	end

	mcl_redstone.is_tick_frozen = true
	local ok, res = craftpipe.place(origin, job.name)
	result.place_ok = ok
	result.place_message = ok and res.message or res
	result.place_stats = ok and res or nil
	if not ok then
		return
	end
	tick(job.settle or 20)

	for _, step in ipairs(job.steps or {}) do
		for _, change in ipairs(step.set or {}) do
			local pos = at(change.pos)
			local node = core.get_node(pos)
			if is_on(node.name) ~= change.on then
				local def = core.registered_nodes[node.name]
				if not def or not def.on_rightclick then
					error("cannot toggle " .. node.name .. " at " .. core.pos_to_string(pos))
				end
				def.on_rightclick(pos, node, nil, ItemStack(""), {type = "node", under = pos, above = pos})
			end
		end
		tick(step.wait or 0)
		local reads = {}
		for i, rel in ipairs(step.read or {}) do
			local node = core.get_node(at(rel))
			reads[i] = {name = node.name, param2 = node.param2, on = is_on(node.name)}
		end
		table.insert(result.steps, reads)
	end
end

core.after(0, function()
	local job = read_json(dir .. "job.json")
	if not job then
		finish("no job.json")
		return
	end
	local p1 = vector.new(job.origin[1] - 1, job.origin[2] - 1, job.origin[3] - 1)
	local p2 = vector.new(job.origin[1] + job.size[1], job.origin[2] + job.size[2],
		job.origin[3] + job.size[3])
	local done = false
	core.emerge_area(p1, p2, function(_, _, remaining)
		if remaining ~= 0 or done then
			return
		end
		done = true
		for x = math.floor(p1.x / 16), math.floor(p2.x / 16) do
			for y = math.floor(p1.y / 16), math.floor(p2.y / 16) do
				for z = math.floor(p1.z / 16), math.floor(p2.z / 16) do
					core.forceload_block(vector.new(x * 16, y * 16, z * 16), true)
				end
			end
		end
		core.after(0, function()
			local ok, err = pcall(run, job)
			finish(not ok and tostring(err) or nil)
		end)
	end)
end)
