cat << 'EOF' > crsz.lua
#!/usr/bin/env lua54

local VERSION = "1.0.0"
local AUTHOR  = "CRSZ"

local C = {
    reset   = "\27[0m", red     = "\27[31m", green   = "\27[32m",
    yellow  = "\27[33m", blue    = "\27[34m", magenta = "\27[35m",
    cyan    = "\27[36m", white   = "\27[37m", bold    = "\27[1m",
}

local function cls() os.execute("clear") end
local function sleep(s) os.execute("sleep " .. s) end

local function readFile(path)
    local f = io.open(path, "r")
    if not f then return nil, "Dosya acilamadi: " .. path end
    local content = f:read("*a")
    f:close()
    return content
end

local function writeFile(path, content)
    local f = io.open(path, "w")
    if not f then return false, "Yazilamadi: " .. path end
    f:write(content)
    f:close()
    return true
end

local LOGO = {
    "  ██████╗██████╗ ███████╗███████╗",
    " ██╔════╝██╔══██╗██╔════╝╚══███╔╝",
    " ██║     ██████╔╝███████╗  ███╔╝ ",
    " ██║     ██╔══██╗╚════██║ ███╔╝  ",
    " ╚██████╗██║  ██║███████║███████╗",
    "  ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝",
    "",
    "  D E O B F U S C A T O R   v" .. VERSION,
}

local function animateBanner()
    cls()
    for i = 1, #LOGO do
        io.write(C.cyan .. C.bold .. LOGO[i] .. C.reset .. "\n")
        io.flush()
        sleep("0.05")
    end
    io.write("\n" .. C.yellow .. "  [ " .. AUTHOR .. " | Termux Edition ]" .. C.reset .. "\n\n")
    sleep("0.3")
end

local function loadingBar(text, duration)
    duration = duration or 1.5
    local width = 30
    io.write(C.green .. "  " .. text .. C.reset .. "\n  ")
    for i = 0, width do
        local pct = math.floor((i / width) * 100)
        local bar = string.rep("█", i) .. string.rep("░", width - i)
        io.write("\r  [" .. C.cyan .. bar .. C.reset .. "] " .. C.yellow .. pct .. "%" .. C.reset)
        io.flush()
        sleep(duration / width)
    end
    io.write("\n\n")
end

local SIGNATURES = {
    { name = "Luraph", pattern = "Luraph" },
    { name = "MoonSec V3", pattern = "MoonSec" },
    { name = "IronBrew2", pattern = "IronBrew" },
    { name = "Prometheus", pattern = "Prometheus" },
    { name = "PSU", pattern = "PSU" },
}

local function detectObfuscator(src)
    local found = {}
    for _, sig in ipairs(SIGNATURES) do
        if src:find(sig.pattern, 1, true) then table.insert(found, sig.name) end
    end
    return found
end

local function decodeEscapes(src)
    local count = 0
    src = src:gsub("\\x(%x%x)", function(h) count = count + 1; return string.char(tonumber(h, 16)) end)
    src = src:gsub("\\(%d%d?%d?)", function(d)
        local n = tonumber(d)
        if n and n <= 255 then count = count + 1; return string.char(n) end
        return "\\" .. d
    end)
    return src, count
end

local function decodeCharChains(src)
    local count = 0
    src = src:gsub("string%.char%s*%(([%d, ]+)%)", function(args)
        local nums = {}
        for n in args:gmatch("%d+") do
            local v = tonumber(n)
            if v and v <= 255 then table.insert(nums, v) end
        end
        if #nums > 0 then count = count + 1; return string.format("%q", string.char(table.unpack(nums))) end
        return "string.char(" .. args .. ")"
    end)
    return src, count
end

local function stripNoise(src)
    src = src:gsub("[ \t]+", " ")
    src = src:gsub("%-%-%[(=*)%[.-%]%1%]", "")
    src = src:gsub("%-%-[^\n]*", "")
    src = src:gsub("\n%s*\n", "\n")
    return src
end

local function readableVars(src)
    local counter = 0
    local map = {}
    src = src:gsub("local%s+([%a_][%w_]*)(%s*=%s*[^%\n]-)(\n)", function(v, val, nl)
        if #v <= 3 and not map[v] then
            counter = counter + 1
            map[v] = "var_" .. counter
            return "local " .. map[v] .. val .. nl
        end
        return "local " .. v .. val .. nl
    end)
    for old, new in pairs(map) do
        src = src:gsub("%f[%w_]" .. old .. "%f[^%w_]", new)
    end
    return src, counter
end

local function processFile(inputPath, outputPath)
    animateBanner()
    loadingBar("Dosya okunuyor...", 0.5)
    local src, err = readFile(inputPath)
    if not src then print(C.red .. "  [HATA] " .. err .. C.reset); return end
    print(C.green .. "  [OK] Boyut: " .. #src .. " byte" .. C.reset .. "\n")

    print(C.yellow .. "  [*] Obfuscator imzasi araniyor..." .. C.reset)
    local detected = detectObfuscator(src)
    if #detected > 0 then
        print(C.magenta .. "  [i] Tespit edildi: " .. table.concat(detected, ", ") .. C.reset)
    else
        print(C.green .. "  [OK] Bilinen imza bulunamadi." .. C.reset)
    end
    print()

    local total = 0
    local stages = {
        { name = "Escape karakterleri",  fn = decodeEscapes },
        { name = "string.char zincirleri", fn = decodeCharChains },
        { name = "Gurultu temizligi",     fn = function(s) return stripNoise(s), 1 end },
        { name = "Degisken okunabilirlik", fn = readableVars },
    }

    for _, stage in ipairs(stages) do
        loadingBar(stage.name .. " isleniyor...", 0.6)
        local newSrc, cnt = stage.fn(src)
        if newSrc and newSrc ~= src then
            total = total + (cnt or 1)
            src = newSrc
            print(C.green .. "  [OK] " .. (cnt or 1) .. " degisiklik" .. C.reset)
        else
            print(C.yellow .. "  [-] Degisiklik yok" .. C.reset)
        end
        print()
    end

    if not outputPath then outputPath = inputPath:gsub("%.lua$", "") .. "_deobf.lua" end
    local ok, werr = writeFile(outputPath, src)
    if not ok then print(C.red .. "  [HATA] " .. werr .. C.reset); return end

    print(C.cyan .. string.rep("─", 50) .. C.reset)
    print(C.green .. C.bold .. "  [✓] TAMAMLANDI - " .. total .. " toplam degisiklik" .. C.reset)
    print(C.cyan .. "  [>] Cikti: " .. outputPath .. C.reset)
    print(C.cyan .. string.rep("─", 50) .. C.reset)
end

local function showMenu()
    animateBanner()
    print(C.yellow .. C.bold .. "  ANA MENU" .. C.reset)
    print(C.cyan .. "  ┌─────────────────────────────────────┐" .. C.reset)
    print(C.cyan .. "  │ " .. C.reset .. C.white .. "[1]" .. C.reset .. " Lua dosyasi deobfuscate et   " .. C.cyan .. "│" .. C.reset)
    print(C.cyan .. "  │ " .. C.reset .. C.white .. "[2]" .. C.reset .. " Obfuscator imza tara         " .. C.cyan .. "│" .. C.reset)
    print(C.cyan .. "  │ " .. C.reset .. C.white .. "[0]" .. C.reset .. " Cikis                        " .. C.cyan .. "│" .. C.reset)
    print(C.cyan .. "  └─────────────────────────────────────┘" .. C.reset)
    io.write("\n  " .. C.green .. "CRSZ> " .. C.reset)
    return io.read()
end

local function main()
    while true do
        local choice = showMenu()
        if choice == "1" then
            io.write("  " .. C.yellow .. "Giris dosyasi: " .. C.reset)
            local input = io.read()
            io.write("  " .. C.yellow .. "Cikis dosyasi (bos = auto): " .. C.reset)
            local output = io.read()
            if output == "" then output = nil end
            processFile(input, output)
            print("\n  " .. C.cyan .. "Devam icin Enter..." .. C.reset)
            io.read()
        elseif choice == "2" then
            io.write("  " .. C.yellow .. "Taranacak dosya: " .. C.reset)
            local input = io.read()
            local src, err = readFile(input)
            if not src then print(C.red .. "  [HATA] " .. err .. C.reset) else
                local found = detectObfuscator(src)
                if #found > 0 then print(C.magenta .. "  [i] Bulunan imzalar: " .. table.concat(found, ", ") .. C.reset)
                else print(C.green .. "  [OK] Bilinen imza yok." .. C.reset) end
            end
            print("\n  " .. C.cyan .. "Devam icin Enter..." .. C.reset)
            io.read()
        elseif choice == "0" then
            cls()
            print(C.cyan .. C.bold .. "\n  CRSZ DEOBFUSCATOR kapatiliyor...\n" .. C.reset)
            loadingBar("Cikis", 0.8)
            os.exit(0)
        end
    end
end

main()
EOF
