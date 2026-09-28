"""Emulate ST39 scene 5 (scene handler, timeline callbacks, GAME timeline/camera interpreter and actor class
controllers) with unicorn, stubbing hardware/audio/render calls and recording every observable event.
"""
import sys, struct, json, re
from pathlib import Path
ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT + "/build/pydeps")
import unicorn
from unicorn import mips_const as M

def s16(v): return (v & 32767) - (v & 32768)
def s32(v): return (v & 0x7FFFFFFF) - (v & 0x80000000)

SLES = GAME = OVL = b""
CTX = 0x8007CEC0
PLAYER = 0x8008C0A0

class Emu:
    def __init__(self, answers):
        self.cpu = cpu = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN)
        cpu.mem_map(0, 0x200000); cpu.mem_map(0x1F800000, 0x2000)
        cpu.mem_write(0x10000, SLES[0x800:]); cpu.mem_write(0xAD000, GAME[0x30:]); cpu.mem_write(0xE7000, OVL[0x30:0x30 + 0x30000])
        self.gpr = [getattr(M, "UC_MIPS_REG_%d" % i) for i in range(32)]
        self.control = [0] * 32; self.data = [0] * 32
        self.events = []; self.tick_info = {}
        self.answers = list(answers); self.answer_log = []
        self.actors = {}  # ptr -> slot
        self.free = [0x80180000 + i * 0x400 for i in range(16)]
        self.unknown = {}
        # GTE hooks at exact addresses
        for base, blob, start, end in ((0x80010000, SLES[0x800:], 0x80010000, 0x80070000), (0x800AD000, GAME[0x30:], 0x800AD000, 0x800E0000), (0x800E7000, OVL[0x30:], 0x800E7000, 0x800F22B8)):
            for off in range(0, min(len(blob), end - base) - 3, 4):
                w = struct.unpack_from("<I", blob, off)[0]; op = w >> 26
                if op == 18 and (w >> 25) & 1 == 0 and ((w >> 21) & 31) in (0, 2, 4, 6) or op == 18 and (w >> 25) & 1 or op in (50, 58):
                    a = base + off; cpu.hook_add(unicorn.UC_HOOK_CODE, self.gte, begin=a, end=a)
        self.stubs = {}
        def stub(addr, name, ret=0, record=True, run=False):
            self.stubs[addr] = (name, ret, record, run); cpu.hook_add(unicorn.UC_HOOK_CODE, self.stub_hook, begin=addr, end=addr)
        # scene side
        for a, n in ((0x80047180, "vibration"), (0x8003D658, "pool_clear"), (0x80048944, "close_windows"), (0x80020160, "sound"),
                     (0x8001BA44, "xa_fade_out"), (0x8001B714, "xa_prepare"), (0x8001B864, "xa_play"), (0x8001392C, "screen_transition"),
                     (0x800CDE4C, "restore_CDE4C"), (0x800C11F0, "restore_C11F0"), (0x800C0F58, "restore_C0F58"), (0x8001B7E8, "xa_select_1B7E8"),
                     (0x80026D10, "depth_cue_mode"), (0x800C0928, "despawn"), (0x8003EA4C, "actor_free_3EA4C"), (0x8003EB7C, "actor_free_3EB7C"),
                     (0x8003E8F8, "spawn_effect_8"), (0x800204DC, "sound_3d_204DC"), (0x800CDD50, "player_ready_CDD50")):
            stub(a, n)
        stub(0x800CDE5C, "player_control")
        stub(0x8001AF94, "xa_ready", 1); stub(0x8001AFD0, "xa_idle", 1)
        stub(0x80048474, "message"); stub(0x800489A0, "message_busy", 0, False)
        stub(0x80016B1C, "camera_shake", 0, True, True)
        stub(0x800C0584, "flag_clear", 0, True, True); stub(0x800C0558, "flag_set", 0, True, True)
        for a, n in ((0x80041318, "face_init"), (0x80041338, "face_eyes"), (0x80041348, "face_mouth"), (0x800417AC, "move_local")):
            stub(a, n, 0, True, True)
        # actor side render/resource
        stub(0x8003DFA4, "resource_ready", 1, False); stub(0x8003F4BC, "actor_control")
        for a in (0x80015A5C, 0x8003F840, 0x80040B04, 0x8003F768, 0x8003B268, 0x800B13B4, 0x8004152C, 0x8003E440, 0x800B13FC, 0x8003B3E4, 0x8003C304, 0x8003EDEC):
            stub(a, "render_%08X" % a, 0, False)
        stub(0x8003E5B0, "alloc_actor", 0, False)
        cpu.hook_add(unicorn.UC_HOOK_MEM_UNMAPPED, self.unmapped)
        self.cur = None
    def unmapped(self, uc, access, address, size, value, data):
        raise RuntimeError("unmapped access %08x at pc %08x" % (address, uc.reg_read(M.UC_MIPS_REG_PC)))
    def r(self, i): return self.cpu.reg_read(self.gpr[i])
    def u8(self, a): return self.cpu.mem_read(a & 0x1FFFFFFF, 1)[0]
    def u16(self, a): return struct.unpack("<H", self.cpu.mem_read(a & 0x1FFFFFFF, 2))[0]
    def u32(self, a): return struct.unpack("<I", self.cpu.mem_read(a & 0x1FFFFFFF, 4))[0]
    def w8(self, a, v): self.cpu.mem_write(a & 0x1FFFFFFF, bytes((v & 255,)))
    def w32(self, a, v): self.cpu.mem_write(a & 0x1FFFFFFF, struct.pack("<I", v & 0xFFFFFFFF))
    def where(self):
        return {"step": self.u8(CTX + 3), "frame": s32(self.u32(CTX + 0x28)), "sub6": self.u8(CTX + 6), "sub7": self.u8(CTX + 7)}
    def record(self, kind, **kw):
        e = {"kind": kind, **self.where(), **kw}
        if self.cur is not None: e["actor_slot"] = self.cur
        self.events.append(e)
    def stub_hook(self, uc, address, size, data):
        name, ret, record, run = self.stubs[address]
        a = [self.r(4), self.r(5), self.r(6), self.r(7)]; ra = self.r(31)
        if name == "alloc_actor":
            p = self.free.pop(0); uc.mem_write(p & 0x1FFFFFFF, bytes(0x400)); self.pending_alloc = p; ret = p
        elif name == "despawn":
            slot = self.actors.pop(a[0], None); self.record("despawn", slot=slot, ptr=hex(a[0])); self.free.append(a[0]) if a[0] else None
        elif name == "message":
            ans = self.answers.pop(0) if self.answers else 3
            self.answer_log.append(ans); flag = 0x680 + ans
            self.cpu.mem_write((0x800A0000 - 0x7AC8 + (flag >> 3)) & 0x1FFFFFFF, bytes((self.u8(0x800A0000 - 0x7AC8 + (flag >> 3)) | (1 << (flag & 7)),)))
            self.record("message", args=[hex(x) for x in a[:3]], simulated_answer=ans, flag_set=hex(flag)); return self._ret(uc, 0, ra)
        if record and name != "despawn":
            caller = ra - 8
            self.record(name, args=[s32(x) for x in a], caller=hex(caller))
        if run: return
        self._ret(uc, ret, ra)
    def _ret(self, uc, ret, ra):
        uc.reg_write(M.UC_MIPS_REG_V0, ret & 0xFFFFFFFF); uc.reg_write(M.UC_MIPS_REG_PC, ra)
    # ---- GTE (copied semantics from tools/cinematics.py NativeCamera) ----
    def write_data(self, index, value): self.data[index] = s16(value) if index in (1, 3, 5, 8, 9, 10, 11) else value & 0xFFFFFFFF
    def gte(self, cpu, address, size, context):
        word = struct.unpack("<I", cpu.mem_read(address & 0x1FFFFFFF, 4))[0]; opcode = word >> 26; source, target, index = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
        if opcode == 18:
            if source in (0, 2): cpu.reg_write(self.gpr[target], (self.control if source == 2 else self.data)[index] & 0xFFFFFFFF)
            elif source == 4: self.write_data(index, cpu.reg_read(self.gpr[target]))
            elif source == 6: self.control[index] = cpu.reg_read(self.gpr[target]) & 0xFFFFFFFF
            else: self.operation(word)
        elif opcode in (50, 58):
            pointer = (cpu.reg_read(self.gpr[source]) + s16(word)) & 0x1FFFFFFF
            if opcode == 50: self.write_data(target, struct.unpack("<I", cpu.mem_read(pointer, 4))[0])
            else: cpu.mem_write(pointer, struct.pack("<I", self.data[target] & 0xFFFFFFFF))
        else: return
        cpu.reg_write(M.UC_MIPS_REG_PC, address + 4)
    def operation(self, word):
        function = word & 63; shift = 12 if word & (1 << 19) else 0; lower = 0 if word & 1024 else -32768; result = []; flag = 0
        if function in (61, 62): result = [s32((self.data[8] * self.data[9 + row] + ((s32(self.data[25 + row]) << shift) if function == 62 else 0)) >> shift) for row in range(3)]
        elif function == 18:
            mk, vk, tk = (word >> 17) & 3, (word >> 15) & 3, (word >> 13) & 3
            base = mk * 8; packed = b"".join(struct.pack("<I", v & 0xFFFFFFFF) for v in self.control[base:base + 5]); matrix = struct.unpack_from("<9h", packed)
            vector = self.data[9:12] if vk == 3 else [s16(self.data[vk * 2]), s16(self.data[vk * 2] >> 16), s16(self.data[vk * 2 + 1])]
            translation = [0] * 3 if tk == 3 else [s32(self.control[5 + tk * 8 + row]) for row in range(3)]
            for row in range(3):
                value = translation[row] << 12
                for column in range(3): value += matrix[row * 3 + column] * vector[column]
                result.append(s32(value >> shift))
        else: raise ValueError("GTE op %02x at" % function)
        for row, value in enumerate(result):
            self.data[25 + row] = value & 0xFFFFFFFF; self.data[9 + row] = max(lower, min(32767, value))
        self.control[31] = flag
    def call(self, function, args=()):
        cpu = self.cpu
        cpu.reg_write(M.UC_MIPS_REG_SP, 0x801FF000); cpu.reg_write(M.UC_MIPS_REG_GP, 0x8007890C); cpu.reg_write(M.UC_MIPS_REG_RA, 0x80000800)
        for i, v in enumerate(args[:4]): cpu.reg_write(self.gpr[4 + i], v & 0xFFFFFFFF)
        try: cpu.emu_start(function, 0x80000800, count=2000000)
        except unicorn.UcError as e: raise RuntimeError("emu error %s pc=%08x fn=%08x" % (e, cpu.reg_read(M.UC_MIPS_REG_PC), function))
        if cpu.reg_read(M.UC_MIPS_REG_PC) != 0x80000800: raise RuntimeError("did not return from %08x pc=%08x" % (function, cpu.reg_read(M.UC_MIPS_REG_PC)))
        return cpu.reg_read(M.UC_MIPS_REG_V0)

def run(answers=(0, 1, 2, 3), max_ticks=12000):
    e = Emu(answers)
    # spawn hook: after 0x800C1010 returns, register slot by record pointer; hook 0x800C1040 (store into ctx+0x2c+slot*4)
    def spawn_hook(uc, address, size, data):
        rec = e.r(16); ptr = e.r(4); slot = e.u8(rec + 1)
        e.actors[ptr] = slot; e.record("spawn", slot=slot, record=hex(rec), ptr=hex(ptr), record_bytes=bytes(uc.mem_read(rec & 0x1FFFFFFF, 20)).hex())
    e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
    # scene object = CTX; start scene: state 0 init
    e.w8(CTX + 4, 0); e.w8(CTX + 5, 0)
    table = 0x800F2204
    snapshots = []
    prev = {}
    for tick in range(max_ticks):
        state = e.u8(CTX + 4)
        if state > 2: break
        handler = e.u32(table + state * 4)
        e.cur = None
        e.call(handler, (CTX,))
        if state == 2 and e.u8(CTX + 5) == 2:
            req = bytes(e.cpu.mem_read(0x80078D08 & 0x1FFFFFFF, 0x1A)); e.record("request_block", bytes=req.hex())
            e.w8(0x80078D08, 0); e.call(handler, (CTX,)); break
        # actor updates
        for ptr, slot in list(e.actors.items()):
            if ptr not in e.actors: continue
            cls = e.u8(ptr + 4); cell = e.u32(0x800ED028 + cls * 4); fn = e.u32(cell)
            e.cur = slot
            e.call(fn, (ptr,))
            # snapshot pose
            pose = (s32(e.u32(ptr + 0x10)), s32(e.u32(ptr + 0x14)), s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 0xFFFF, e.u8(ptr + 0xA0), e.u8(ptr + 8), e.u8(ptr + 9), e.u8(ptr + 0xC))
            if prev.get(slot) != pose:
                snapshots.append({"t": tick, **e.where(), "slot": slot, "pos16": pose[:3], "yaw": pose[3], "control": pose[4], "mode8": pose[5], "mode9": pose[6], "modeC": pose[7]})
                prev[slot] = pose
        e.cur = None
        ppose = (s32(e.u32(PLAYER + 0x10)), s32(e.u32(PLAYER + 0x14)), s32(e.u32(PLAYER + 0x18)), e.u16(PLAYER + 0x2A), e.u8(PLAYER + 0x1A0), e.u8(PLAYER + 0x1A1), e.u8(PLAYER) & 2)
        if prev.get("player") != ppose:
            snapshots.append({"t": tick, **e.where(), "slot": "player", "pos16": ppose[:3], "yaw": ppose[3], "face_eye_frame": ppose[4], "face_mouth_frame": ppose[5], "flag2": ppose[6]})
            prev["player"] = ppose
        if state == 2 and e.u8(CTX + 5) >= 3: break
    return e, snapshots, tick

"""Build assets/levels/ST39/scene_05.json and scene_05_callbacks.json for ST39 scene 5 (Game Start intro).
Static data is decoded from DAT/ST39T.BIN; callback programs are hand-translated from the ST39T disassembly
(0x800EB790..0x800ECC10) and cross-checked against a unicorn emulation (Emu above) of the original code;
actor controller events/tracks are taken from that emulation of the unchanged ST39T class controllers."""
import sys, json, struct
sys.dont_write_bytecode = True
import unicorn

def rd(a, n): o = 0x30 + a - 0x800E7000; return OVL[o:o + n]
def u32(a): return struct.unpack("<I", rd(a, 4))[0]
OUT = ROOT + "/assets/levels/ST39/"
H = lambda v: "0x%08x" % v
SRC_MSG = "SLES0x80048474/0x800489A0"

# ---------------------------------------------------------------- camera stream / timeline
def commands():
    out = []; a = 0x800F1BAC
    while True:
        w = u32(a); op = w >> 24
        size = 16 if 0x10 <= op <= 0x1A else 8 if op in (0x40, 0x41) else 20 if op == 0x42 else 4
        words = list(struct.unpack("<%dI" % (size // 4), rd(a, size)))
        item = {"source_ram": H(a), "opcode": op, "words": words}
        if op in (0x40, 0x41): item["actor_record"] = {"source_ram": H(words[1]), "bytes": rd(words[1], 20).hex()}
        if op in (0x18, 0x19):
            mode = (w >> 16) & 7
            item["interpolation"] = {"ticks": w & 0xFFFF, "ease_mode": mode, "ease": {0: "linear", 1: "cosine_in_out", 2: "quadratic_ease_out", 3: "quadratic_ease_in"}.get(mode, "linear"),
                                     "target_fixed": [s32(x) / 65536 for x in words[1:]], "channel": "focus" if op == 0x18 else "orbit"}
        out.append(item); a += size
        if op == 0xFF: break
    assert a == 0x800F1F14, hex(a)
    return out
def timeline():
    out = []; a = 0x800F1F14
    while True:
        p, s, d, cb = struct.unpack("<BBhI", rd(a, 8))
        if p == 255: break
        out.append({"phase": p, "step": s, "duration": d, "callback": "0x%x" % cb, "source_ram": "0x%x" % a}); a += 8
    return out

# ---------------------------------------------------------------- actor records
MANIFEST = {}
CLASS_MODEL = {0x30: 0, 0x39: 1, 0x47: 2, 0x63: 3}
CLASS_NOTE = {0x30: "Flutter exterior (largest model, ~6 units; pool type 0x20 class 0x30, controller ST39T 0x800E7594)",
              0x39: "humanoid with face channels, 0.68 units tall, 21 controls (class 0x39; variant 0 controller 0x800E7B34, variant 1 controller 0x800E7E58 + answer lip-sync 0x800E897C) - identity unverified (likely Roll)",
              0x47: "flat 2-node prop 0.3x0.3 units, 6 controls (class 0x47, controller ST39T 0x800E8ED0) - identity unverified",
              0x63: "small 8-node character with face channel, 0.19 units tall, 13 controls (class 0x63; variant 0 0x800E9178, variant 1 0x800E9514) - identity unverified (likely Data)"}
RECORD_AREA = {0x800F1B0C: 0, 0x800F1B20: 1, 0x800F1B34: 1, 0x800F1B48: 1, 0x800F1B5C: 0, 0x800F1B70: 1, 0x800F1B84: 1, 0x800F1B98: 1}
def actor_records():
    out = []
    for a in sorted(RECORD_AREA):
        b = rd(a, 20); cls = b[4]; x, y, z, yaw = struct.unpack_from("<3hH", b, 12); idx = CLASS_MODEL[cls]
        model = MANIFEST["models"][idx]; exp = model.get("export", {})
        turns = -(yaw / 4096.0)
        if turns < -0.5: turns += 1.0
        mfile = model["file"]
        out.append({"source_ram": H(a), "slot": b[1], "class_note": CLASS_NOTE[cls],
                    "entry": {"stage": "ST39", "area": RECORD_AREA[a], "source_record_ram": H(a), "source_bytes_hex": b.hex(), "pool_type": b[2], "actor_class": cls, "actor_state": b[5], "resource_variant": b[6],
                              "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": yaw, "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": idx, "model_file": mfile},
                    "model": {"file": mfile, "source_archive": "DAT/ST39.BIN section 0x3000 (ST39_03000)", "source_model_index": idx, "source_flags": model["flags"], "class_from_flags": model["flags"] >> 8,
                              **{k: exp[k] for k in ("mesh_offset", "texture_tpage", "texture_clut", "bone_count", "control_count", "face_count", "lod_counts", "native_scale_raw", "animations", "control_map", "source_materials", "source_surfaces", "face_dims") if k in exp},
                              "model_file": mfile, "model_index": idx,
                              "alternate_bank": {0x47: "ST3901_03000/model_001.glb (flags 0x4720)", 0x63: "ST3901_03000/model_002.glb (flags 0x6320)"}.get(cls)}})
    return out

# ---------------------------------------------------------------- XA descriptors, face tables
def xa_desc(i):
    a = 0x800ED774 + i * 8; raw = rd(a, 8)
    return {"id": i, "descriptor_ram": H(a), "descriptor_bytes": raw.hex(), "archive_index": raw[0], "archive": "XA/PAL_37.XA" if raw[0] == 2 else None,
            "sector_start": (raw[1] << 16) | struct.unpack_from("<H", raw, 2)[0], "sector_end": (raw[5] << 16) | struct.unpack_from("<H", raw, 6)[0], "channel": raw[4] & 31, "flags": raw[4] & 0xE0}
def face_table(base, limit):
    seqs = []
    ptrs = [u32(base + i * 4) for i in range(limit)]
    for i, p in enumerate(ptrs):
        frames = []; a = p
        while True:
            f, dur, op, arg = rd(a, 4)
            frames.append({"frame": f, "ticks": dur, "op": op, "arg": arg}); a += 4
            if op in (1, 2, 4) or len(frames) > 64: break
        seqs.append({"sequence": i, "source_ram": H(p), "entries": frames})
    return {"table_ram": H(base), "semantics": "SLES0x80041358: each tick writes entry.frame to the channel byte, counts entry.ticks, then op 1=hold (channel stops), 2=restart at entry 0, 4=index+=arg, other=next entry", "sequences": seqs}

# ---------------------------------------------------------------- emulation
def emulate(answers=(0, 1, 2, 3)):
    e = Emu(answers)
    def spawn_hook(uc, address, size, data):
        rec = e.r(16); ptr = e.r(4); slot = e.u8(rec + 1); e.actors[ptr] = slot
        e.record("spawn", slot=slot, record=H(rec))
    e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
    tracks = {}; ticks = 0
    for tick in range(20000):
        st = e.u8(CTX + 4)
        if st > 2: break
        h = e.u32(0x800F2204 + st * 4); e.cur = None
        if st == 2 and e.u8(CTX + 5) == 2:
            e.record("request_block", bytes=bytes(e.cpu.mem_read(0x80078D08 & 0x1FFFFFFF, 0x1A)).hex()); e.w8(0x80078D08, 0); e.call(h, (CTX,)); break
        e.call(h, (CTX,))
        w = e.where()
        for ptr, slot in list(e.actors.items()):
            if ptr not in e.actors: continue
            fn = e.u32(e.u32(0x800ED028 + e.u8(ptr + 4) * 4)); e.cur = slot; e.call(fn, (ptr,))
            tracks.setdefault(slot, []).append((tick, w["step"], w["frame"], s32(e.u32(ptr + 0x10)), s32(e.u32(ptr + 0x14)), s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 4095, w["sub7"]))
        e.cur = None; ticks = tick
    return e, tracks, ticks

def compress(rows):
    """keep keyframes where per-tick delta changes (piecewise linear in native ticks)"""
    if not rows: return []
    keep = [rows[0]]
    for i in range(1, len(rows) - 1):
        a, b, c = rows[i - 1], rows[i], rows[i + 1]
        d1 = tuple(b[k] - a[k] for k in (3, 4, 5, 6)); d2 = tuple(c[k] - b[k] for k in (3, 4, 5, 6))
        if d1 != d2 or b[1] != a[1] or c[1] != b[1]: keep.append(b)
    keep.append(rows[-1])
    out = []
    for r in keep:
        k = {"step": r[1], "tick": r[2], "position_raw": [round(r[3] / 65536, 5), round(r[4] / 65536, 5), round(r[5] / 65536, 5)], "yaw_raw": r[6]}
        if not out or out[-1] != k: out.append(k)
    return out

def main():
    global SLES, GAME, OVL, MANIFEST
    SLES = open(ROOT + "/build/disc-assets/SLES_035.56", "rb").read(); GAME = open(ROOT + "/build/disc-assets/COMMON/GAME.BIN", "rb").read(); OVL = open(ROOT + "/build/disc-assets/DAT/ST39T.BIN", "rb").read()
    MANIFEST = json.load(open(ROOT + "/assets/levels/ST39/models/ST39_03000/manifest.json", encoding="utf-8"))
    cmds = commands(); tl = timeline(); recs = actor_records()
    import shutil, models as player_models, world
    disc = Path(ROOT) / "build/disc-assets"; player_payload = (disc / "COMMON/PL00P000.BIN").read_bytes()[0x30:]; face_word = struct.unpack_from("<4I", player_payload, 0x60)[2]
    vram, _ = player_models.textures(disc / "COMMON/PL00T.BIN"); world.texture_uploads((disc / "DAT/ST39T.BIN").read_bytes(), vram, "DAT/ST39T.BIN")
    (Path(OUT) / "player_face_page1.png").write_bytes(player_models.texture_page(vram, face_word >> 16, (face_word & 0xFFFF) + 1))
    actors = Path(OUT) / "actors"; actors.mkdir(parents=True, exist_ok=True)
    for record in recs:
        source = Path(ROOT) / record["model"]["file"]; runtime = "assets/levels/ST39/actors/" + source.name
        for item in source.parent.glob(source.stem + "*"):
            if item.suffix in (".glb", ".png"): shutil.copy2(item, actors / item.name)
        record["entry"]["model_file"] = record["model"]["model_file"] = runtime
    e, tracks, ticks = emulate()
    ev = e.events
    # ---------------- cross-check hand translation against emulation (player controls / faces)
    emu_player = [(x["step"], x["frame"], x["args"][0], x["args"][1]) for x in ev if x["kind"] == "player_control"]
    emu_face = [(x["step"], x["frame"], x["kind"], x["args"][1]) for x in ev if x["kind"] in ("face_eyes", "face_mouth") and x.get("actor_slot") is None]

    P = lambda c, src, start=0: {"op": "player_control", "control": c, "start_record": start, "source": src, "native": "GAME0x800CDE5C(%d,%d,1)" % (c, start)}
    EY = lambda s, src: {"op": "player_face", "channel": "eyes", "sequence": s, "source": src, "native": "SLES0x80041338(ctx+0xB0,%d,0)" % s}
    MO = lambda s, src: {"op": "player_face", "channel": "mouth", "sequence": s, "source": src, "native": "SLES0x80041348(ctx+0xB0,%d,0)" % s}
    VIS = lambda on, src: {"op": "player_render_flag", "set": on, "source": src, "native": "0x8008C0A0 byte0 %s 0x02" % ("|=" if on else "&=~")}
    SKY = lambda h, p, src: dict({"op": "sky_gradient", "horizon_raw": h, "source": src, "native": "0x800966C0+0x16" + ("/+0x18" if p is not None else "")}, **({"param_18_raw": p} if p is not None else {}))
    SND = lambda i, src: {"op": "play_sound", "id": i, "source": src, "native": "SLES0x80020160(0x%X)" % i}
    AREA = lambda area, pos, facing, src: {"op": "area_change", "stage": "ST39", "area": area, "position_raw": pos, "facing_raw": facing, "fade_arrival": 255, "fade_exit": 255, "request_type": -1, "source": src,
                                          "native": "request block 0x80078D08: +0=-1 +4=0x39 +5=%d +0x10/12/14=%s +0x16=%d +0x18=0xFF +0x19=0xFF; ctx+6=0; GAME0x800C0EA8(1)" % (area, pos, facing)}
    ASTATE = lambda slot, rec, v, src: {"op": "actor_state", "slot": slot, "record": rec, "field_0x0C": v, "field_0x0D": 0, "source": src}
    def act(tick, *ops): return [dict(o, tick=tick) for o in ops]

    seg = {}
    # step 0 (0x800EBB7C): frame-switched, callback-advanced
    seg["0:0"] = {"source": "0x800EBB7C", "area": 0, "actions": act(300, SKY(0x280, 0, "0x800EBBAC")),
                  "program": [{"op": "minimum_tick", "tick": 565, "source": "0x800EBB9C"}, AREA(1, [0, 0, -184], 0, "0x800EBBC4..0x800EBC14"), {"op": "advance", "source": "GAME0x800C0EA8(1) at 0x800EBC10"}]}
    # step 1 (0x800EBC28) duration 130
    seg["0:1"] = {"source": "0x800EBC28", "area": 1,
                  "actions": act(0, {"op": "pool_clear", "mask": 0xFFE, "flags": 0x80, "source": "0x800EBC50", "native": "SLES0x8003D658(0xFFE,0x80)"}, VIS(True, "0x800EBC68"), SKY(0x190, 0x180, "0x800EBC78/0x800EBC84"),
                                 SND(0x29F, "0x800EBC80"), {"op": "sound_latch", "value": 1, "source": "0x800EBC8C", "native": "ctx+0x0D=1 (finish plays 0x2A0 when set)"},
                                 P(0x80, "0x800EBCD8"), EY(0, "0x800EBCEC"), MO(0, "0x800EBCFC"))
                  + act(30, EY(1, "0x800EBD50"))
                  + act(65, P(0x81, "0x800EBD20"), EY(0, "0x800EBD30"), ASTATE(2, "0x800f1b34", 1, "0x800EBD38..0x800EBD48 (ctx+0x34 -> slot 2)"))
                  + act(110, EY(2, "0x800EBD50")),
                  "program": []}
    seg["0:2"] = {"source": "0x800EBD6C", "area": 1, "actions": act(0, SKY(0x26C, None, "0x800EBD88"), VIS(False, "0x800EBD90")), "program": []}
    # step 3 (0x800EBD9C) duration 1020
    roll = []
    for f in range(0x14A, 0x14A + 0x21):
        v1 = f - 0x14A; off = 0x800 + 0x80073E4C - 0x80010000 + ((v1 << 8) & 0x3F00)
        roll.append(s16(struct.unpack_from("<H", SLES, off)[0]) >> 5)
    seg["0:3"] = {"source": "0x800EBD9C", "area": 1,
                  "actions": act(0, VIS(True, "0x800EBDCC"), P(0x82, "0x800EBE68"), EY(3, "0x800EBE7C"), MO(1, "0x800EBFB0"))
                  + act(100, MO(2, "0x800EBE90/0x800EBFB0")) + act(240, MO(1, "0x800EBE9C/0x800EBFB0"))
                  + act(330, P(0x83, "0x800EBEAC"), EY(4, "0x800EBEC0"), MO(3, "0x800EBED0"), ASTATE(2, "0x800f1b34", 2, "0x800EBEE4..0x800EBEF4"),
                        {"op": "camera_shake", "magnitude_raw": 0x200, "decay_raw": 0x10, "source": "0x800EBEF0", "native": "SLES0x80016B1C(0,0x200,0x10): camera state 0x8007D010+0xD8=0x200,+0xDC=0x10; GAME0x800C24C0 subtracts (+0xD8>>8) from focus Y"},
                        {"op": "vibration", "args_raw": [0, 0x011820FF], "source": "0x800EBF00", "native": "SLES0x80047180(0,0x011820FF) -> gp+0x750..0x754 = 0x00,0x00,0xFF,0x20,0x18", "unverified": True, "note": "pad actuator request; byte meaning (strength/duration) unverified"})
                  + act(350, EY(5, "0x800EBF1C"), MO(4, "0x800EBFB0")) + act(440, EY(6, "0x800EBF38"), MO(5, "0x800EBFB0")) + act(520, MO(4, "0x800EBF4C/0x800EBFB0"))
                  + act(820, P(0x84, "0x800EBF60"), EY(7, "0x800EBF74"), MO(6, "0x800EBFB0")) + act(920, P(0x85, "0x800EBF8C"), EY(8, "0x800EBFA0"), MO(7, "0x800EBFB0")),
                  "camera_roll": {"op": "camera_roll", "from_tick": 330, "through_tick": 362, "values_raw": roll, "otherwise": 0, "source": "0x800EBFB8..0x800EBFF8",
                                  "native": "0x80096D64 (= camera ctx 0x80096D50+0x14) = s16(SLES trig 0x80073E4C[(frame-330)*64].sin)>>5, else 0; GAME0x800C2518 passes it as roll to SLES0x80015B6C"},
                  "program": []}
    seg["0:4"] = {"source": "0x800EC010", "area": 1,
                  "actions": act(0, P(0x86, "0x800EC074"), EY(9, "0x800EC088"), MO(9, "0x800EC098"), ASTATE(2, "0x800f1b34", 5, "0x800EC0A0..0x800EC0B0"))
                  + act(240, EY(10, "0x800EC0BC"), MO(8, "0x800EC108")) + act(390, MO(9, "0x800EC0D0/0x800EC108")) + act(530, P(0x87, "0x800EC0E4"), EY(11, "0x800EC0F8"), MO(10, "0x800EC108")),
                  "program": [{"op": "minimum_tick", "tick": 605, "source": "0x800EC05C"}, AREA(0, [0, 0, 0], 0, "0x800EC118..0x800EC160"), {"op": "advance", "source": "GAME0x800C0EA8(1) at 0x800EC15C"}]}
    seg["0:5"] = {"source": "0x800EC178", "area": 0,
                  "actions": act(0, SKY(0x244, -0x180, "0x800EC1AC/0x800EC1B8"), VIS(False, "0x800EC1C4"), SND(0x2A0, "0x800EC1C0"), {"op": "sound_latch", "value": 0, "source": "0x800EC1CC"}),
                  "program": [{"op": "minimum_tick", "tick": 120, "source": "0x800EC1D0"}, AREA(1, [0x40, 0, -0xA0], 0, "0x800EC1D8..0x800EC22C"), {"op": "advance", "source": "GAME0x800C0EA8(1) at 0x800EC228"}]}
    seg["0:6"] = {"source": "0x800EC240", "area": 1, "substate_gate": "actions run only while ctx+6 == 0",
                  "actions": act(0, {"op": "pool_clear", "mask": 0xFFE, "flags": 0x80, "source": "0x800EC3A0"}, VIS(True, "0x800EC3C4"), P(0x88, "0x800EC3C0"), EY(12, "0x800EC3D4"), MO(10, "0x800EC3E4"), SND(0x29F, "0x800EC3EC"), {"op": "sound_latch", "value": 1, "source": "0x800EC3FC"})
                  + act(390, P(0x89, "0x800EC408"), EY(11, "0x800EC41C"), MO(12, "0x800EC530")) + act(520, P(0x8A, "0x800EC434"), EY(11, "0x800EC448"), MO(13, "0x800EC530"))
                  + act(750, MO(14, "0x800EC45C")) + act(770, MO(15, "0x800EC468")) + act(780, MO(14, "0x800EC470")) + act(790, MO(15, "0x800EC47C"))
                  + act(1500, P(0x8B, "0x800EC48C"), EY(14, "0x800EC4A0"), MO(11, "0x800EC530")) + act(1690, P(0x8C, "0x800EC4B4/0x800EC55C"))
                  + act(1875, P(0x8D, "0x800EC4C0"), EY(12, "0x800EC4D4"), MO(10, "0x800EC52C/0x800EC530")) + act(1920, ASTATE(7, "0x800f1b98", 3, "0x800EC4E4..0x800EC550 (ctx+0x48 -> slot 7)"))
                  + act(2140, P(0x8E, "0x800EC4F8"), EY(12, "0x800EC50C"), MO(16, "0x800EC530")) + act(2150, MO(10, "0x800EC52C")) + act(2160, MO(16, "0x800EC520")) + act(2190, MO(10, "0x800EC52C"))
                  + act(2290, ASTATE(7, "0x800f1b98", 4, "0x800EC540..0x800EC550")) + act(2310, P(0x8F, "0x800EC55C")),
                  "program": [{"op": "minimum_tick", "tick": 2420, "source": "0x800EC390"},
                              {"op": "xa_fade_out", "speed": 8, "only_if_xa_ready": True, "source": "0x800EC56C..0x800EC580", "native": "if SLES0x8001AF94(): SLES0x8001BA44(8)"},
                              {"op": "skip_lock", "set": True, "source": "0x800EC58C", "native": "ctx 0x8007CEC0 byte0 |= 0x20 (GAME0x800C10B4 ignores Start while set)"},
                              {"op": "wait_xa_idle", "source": "0x800EC5A0", "native": "SLES0x8001AFD0() (0x80078DC8 bit0 clear)"},
                              {"op": "advance", "source": "0x800EC5B0..0x800EC5B4"}]}
    seg["0:7"] = {"source": "0x800EC5D0", "area": 1,
                  "motion": [{"actor": "player", "op": "player_axis_set", "axis": "x", "from_tick": 0, "through_tick": 16, "value_raw": "0x40 + tick", "source": "0x800EC600..0x800EC60C", "native": "0x8008C0B2 (player +0x12, X integer) = ctx+0x28 + 0x40 while ctx+6==0"}],
                  "program": [{"op": "minimum_tick", "tick": 16, "source": "0x800EC614"},
                              {"op": "label", "name": "ask", "source": "0x800EC668 (ctx+7 state 0)"},
                              {"op": "message", "index": 0, "state": 1, "source": SRC_MSG + " at 0x800EC674/0x800EC68C", "note": "4-way choice; bank messages 1..4 set event flags 0x680..0x683 (cancel -> 4 -> 0x683)"},
                              {"op": "select_by_flags", "flags": [0x680, 0x681, 0x682, 0x683], "store": "answer", "keep_previous_if_none": True, "initial": 0, "source": "0x800EC69C..0x800EC6E8"},
                              {"op": "play_xa", "descriptor_by_answer": [0x58, 0x59, 0x5A, 0x5B], "select": "answer", "descriptor_table_ram": "0x800F2210", "source": "0x800EC6EC..0x800EC774", "native": "wait !(0x80078DBA&1); SLES0x8001B714(id); wait !(0x80078DBA&2); SLES0x8001B864(id); wait SLES0x8001AF94()"},
                              {"op": "director_state", "state": 5, "source": "ctx+7 = 5 (actor slot 5 controller 0x800E897C starts the answer reaction on this value)"},
                              {"op": "jump_if", "answer": 3, "to": "leave", "source": "0x800EC788..0x800EC794"},
                              {"op": "wait_flag_clear", "flag": "0x680 + answer", "source": "0x800EC798..0x800EC7A0"},
                              {"op": "wait_xa_idle", "source": "0x800EC7A8"},
                              {"op": "jump", "to": "ask", "source": "0x800EC7B8 (ctx+7 = 0)"},
                              {"op": "label", "name": "leave"},
                              {"op": "wait_flag_clear", "flag": 0x683, "source": "0x800EC7C0..0x800EC7C8"},
                              {"op": "advance", "source": "0x800EC7D0..0x800EC7D4"}]}
    seg["0:8"] = {"source": "0x800EC7EC", "area": 1,
                  "motion": [{"actor": "player", "op": "player_axis_set", "axis": "x", "from_tick": 0, "through_tick": 16, "value_raw": "0x50 - tick", "source": "0x800EC81C..0x800EC82C"}],
                  "actions": act(16, {"op": "skip_lock", "set": False, "source": "0x800EC840..0x800EC850", "native": "ctx byte0 &= ~0x20; ctx+6 = 1"})
                  + act(40, P(0x90, "0x800EC8B0"), EY(16, "0x800EC8C4"), MO(11, "0x800EC934")) + act(80, MO(20, "0x800EC8D8/0x800EC934")) + act(130, MO(11, "0x800EC8E0/0x800EC934"))
                  + act(230, EY(17, "0x800EC8F8"), MO(21, "0x800EC934")) + act(280, P(0x91, "0x800EC910"), EY(18, "0x800EC924"), MO(17, "0x800EC934")),
                  "substate_gate": "ticks 40..280 actions run only after ctx+6 became 1 at tick 16", "program": []}
    seg["0:9"] = {"source": "0x800EC94C", "area": 1,
                  "actions": act(0, P(0x92, "0x800ECA50"), EY(19, "0x800ECA64"), MO(18, "0x800ECA74"),
                                 {"op": "player_axis_set", "axis": "x", "value_raw": 0x50, "source": "0x800ECA80", "native": "player +0x12 = 0x50"},
                                 {"op": "player_yaw_set", "yaw_raw": 0x60, "source": "0x800ECA84", "native": "player +0x2A = 0x60"})
                  + act(5, P(0x93, "0x800ECA9C")) + act(30, P(0x94, "0x800ECA9C")) + act(40, P(0x95, "0x800ECAB0"), EY(12, "0x800ECAC0"))
                  + act(80, MO(19, "0x800ECAD0/0x800ECB30")) + act(120, MO(13, "0x800ECADC/0x800ECB30")) + act(200, P(0x96, "0x800ECAF0"), EY(13, "0x800ECB04"), MO(16, "0x800ECB30"))
                  + act(220, P(0x97, "0x800ECB20"), MO(10, "0x800ECB30"))
                  + act(225, P(1, "0x800ECB4C (ctx+6==1, one tick after tick 224 set it)", 4), {"op": "player_yaw_add", "delta_raw": 0x800, "source": "0x800ECB54..0x800ECB60"}),
                  "motion": [{"actor": "player", "from_tick": 225, "velocity_raw": [0, 0, -0x200], "source": "0x800ECB74..0x800ECB84", "native": "SLES0x800417AC(player,0,0,-0x200) each tick while ctx+6==2 (emulated: 32 raw units/tick along facing)"}],
                  "program": [{"op": "minimum_tick", "tick": 250, "source": "0x800ECBA8..0x800ECBB0"},
                              {"op": "fade", "type": 0x12, "wait": True, "source": "0x800ECBBC (SLES0x8001392C(0x12,0)); wait 0x80078F01==0 at 0x800ECBE0", "native": "also ctx byte0 |= 0x04 (blocks skip)"},
                              {"op": "advance", "source": "0x800ECBF0..0x800ECBF4 (timeline ends -> finish handler 0x800EB9F4)"}]}
    for k, v in seg.items(): v.setdefault("program", [])

    # cross-check
    hand_p = []; hand_f = []
    for k, v in seg.items():
        step = int(k.split(":")[1])
        for a in v.get("actions", []):
            if a["op"] == "player_control": hand_p.append((step, a["tick"], a["control"], a["start_record"]))
            if a["op"] == "player_face": hand_f.append((step, a["tick"], "face_eyes" if a["channel"] == "eyes" else "face_mouth", a["sequence"]))
    emu_p_scene = [x for x in emu_player if not (x[0] == 0 and x[1] == 0 and x[2] == 0)]  # drop finish-handler call
    emu_f_scene = [x for x in emu_face if not (x[0] == 0 and x[1] in (0, 1))]
    cross = {"player_control_match": sorted(hand_p) == sorted(emu_p_scene), "player_face_match": sorted(set(hand_f)) == sorted(set(emu_f_scene)),
             "player_control_only_hand": sorted(set(hand_p) - set(emu_p_scene)), "player_control_only_emu": sorted(set(emu_p_scene) - set(hand_p)),
             "face_only_hand": sorted(set(hand_f) - set(emu_f_scene)), "face_only_emu": sorted(set(emu_f_scene) - set(hand_f))}

    # ---------------- actor controllers from emulation
    ctrl = {}
    rec_by_slot = {r["slot"]: r for r in recs}
    xa_ready7 = [x["frame"] for x in ev if x["kind"] == "xa_ready" and x["step"] == 7]
    def answer_of(frame):
        k = -1
        for i, f in enumerate(xa_ready7):
            if frame > f: k = i
        return k
    for slot, rows in sorted(tracks.items(), key=lambda kv: str(kv[0])):
        r = rec_by_slot[slot]; cls = r["entry"]["actor_class"]; var = r["entry"]["resource_variant"]
        fn = {0x30: "0x800E7594", 0x47: "0x800E8ED0", 0x39: ["0x800E7B34", "0x800E7E58"][var], 0x63: ["0x800E9178", "0x800E9514", "0x800E96C0"][var]}[cls]
        sev = [x for x in ev if x.get("actor_slot") == slot]
        controls = [x for x in sev if x["kind"] == "actor_control"]
        startup = controls[0] if controls else None
        events = []; answer_events = {}
        for x in sev:
            item = None
            if x["kind"] == "actor_control" and x is not startup: item = {"op": "control", "control": x["args"][1], "start_record": x["args"][2], "native": "SLES0x8003F4BC via %s" % x["caller"]}
            elif x["kind"] in ("face_eyes", "face_mouth"): item = {"op": "actor_face", "channel": "eyes" if x["kind"] == "face_eyes" else "mouth", "sequence": x["args"][1], "native": "%s via %s" % ("SLES0x80041338" if x["kind"] == "face_eyes" else "SLES0x80041348", x["caller"])}
            elif x["kind"] == "face_init": item = {"op": "actor_face_init", "eye_table_ram": H(x["args"][1] & 0xFFFFFFFF), "mouth_table_ram": H(x["args"][2] & 0xFFFFFFFF) if x["args"][2] else None, "native": "SLES0x80041318 via %s" % x["caller"]}
            elif x["kind"] == "flag_clear": item = {"op": "event_clear", "id": x["args"][0], "native": "GAME0x800C0584 via %s" % x["caller"]}
            elif x["kind"] == "spawn_effect_8": item = {"op": "effect_spawn", "native": "SLES0x8003E8F8 (pool 8) via %s" % x["caller"], "args_raw": [a & 0xFFFFFFFF for a in x["args"][:2]], "unverified": True}
            if item is None: continue
            if x["step"] == 7 and slot == 5 and answer_of(x["frame"]) >= 0:
                ans = answer_of(x["frame"]); answer_events.setdefault(str(ans), []).append(dict(item, after_xa_ready_ticks=x["frame"] - xa_ready7[ans]))
            else:
                events.append(dict(item, step=x["step"], tick=x["frame"]))
        prof = {"tick_note": "tick = ctx+0x28 as read by the actor after GAME0x800C0D70 incremented it (actors emulated after the scene update; native ordering of scene vs actor update is unverified, +-1 tick)", "source": "ST39T " + fn + " (emulated with unicorn: class function run once per native tick after the scene update; render/animation helpers stubbed)", "class": cls, "variant": var, "record": r["source_ram"]}
        if startup: prof["startup_control"] = startup["args"][1]; prof["startup_start_record"] = startup["args"][2]
        prof["events"] = events
        if answer_events: prof["answer_reactions"] = {"relative_to": "frame at which play_xa reported ready (ctx+7 becomes 5) for that answer", "source": "ST39T 0x800E897C (called from 0x800E8764 while ctx+3==7)", "by_answer": answer_events,
                                                      "flag_clear_after_ticks": {"0": 450, "1": 310, "2": 270, "3": 120}, "flag_clear_source": "0x800E8BE8 (0x680@0x1C2), 0x800E8CDC (0x681@0x136), 0x800E8D8C (0x682@0x10E), 0x800E8E3C (0x683@0x78, then mode 5)"}
        prof["track"] = {"op": "actor_track", "interpolation": "linear between keyframes in native ticks (keyframes where per-tick delta changes)", "keyframes": compress(rows)}
        ctrl[str(slot)] = prof

    # player face tables & actor face tables
    faces = {"player_eyes": face_table(0x800F2018, 20), "player_mouth": face_table(0x800F21AC, 22)}
    for prof in ctrl.values():
        events = prof["events"] + [e for group in prof.get("answer_reactions", {}).get("by_answer", {}).values() for e in group]
        for channel, key in (("eyes", "eye_table_ram"), ("mouth", "mouth_table_ram")):
            tables = {e[key].lower() for e in events if e["op"] == "actor_face_init" and e.get(key)}; used = [e["sequence"] for e in events if e["op"] == "actor_face" and e["channel"] == channel]
            for table in tables:
                if used: faces[table] = face_table(int(table, 16), max(used) + 1)

    xa = {"intro": xa_desc(0x47), "answers": [xa_desc(i) for i in (0x58, 0x59, 0x5A, 0x5B)], "descriptor_table": "0x800ED774 (ST39T 0x800E7148 stores it at 0x80078DD8; SLES0x8001B9D0 indexes 8-byte descriptors)",
          "prepare": "SLES0x8001B714", "play": "SLES0x8001B864", "ready": "SLES0x8001AF94", "idle": "SLES0x8001AFD0", "fade_out": "SLES0x8001BA44"}

    req = [x for x in ev if x["kind"] == "request_block"][0]["bytes"]
    scene = {"stage": "ST39", "area": 0, "scene_id": 5, "native_tick_hz": 25, "callback_contract_file": "scene_05_callbacks.json",
             "commands": cmds, "timeline": tl, "actors": recs,
             "player": {"scene_init": {"position_raw": [0, 0, 0], "yaw_raw": None, "yaw_note": "init (0x800EB86C..0x800EB89C) zeroes player +0x10/+0x14/+0x18 (+0xF0/+0xF4, face bytes +0x1A0/+0x1A1); yaw +0x2A is not written (inherits area-entry yaw)", "unverified_yaw": True},
                        "per_area_entries": [
                            {"area": 0, "when": "scene start (Game Start enters ST39:0)", "position_raw": [0, 0, 0], "source": "0x800EB890..0x800EB898"},
                            {"area": 1, "when": "step 0 tick 565", "position_raw": [0, 0, -184], "facing_raw": 0, "source": "0x800EBBC4..0x800EBC14"},
                            {"area": 0, "when": "step 4 tick 605", "position_raw": [0, 0, 0], "facing_raw": 0, "source": "0x800EC118..0x800EC160"},
                            {"area": 1, "when": "step 5 tick 120", "position_raw": [0x40, 0, -0xA0], "facing_raw": 0, "source": "0x800EC1D8..0x800EC22C"},
                            {"area": 1, "when": "step 9 tick 0", "position_raw": [0x50, None, None], "yaw_raw": 0x60, "source": "0x800ECA7C..0x800ECA84 (only X and yaw written)"}],
                        "camera_opcode_0x42_used": False},
             "face_tables": faces,
             "xa": xa,
             "audio_cues": [{"kind": "xa", "id": 0x47, "when": "scene init states 2..4 (0x800EB8F0/0x800EB918); timeline starts only after SLES0x8001AF94 reports ready (0x800EB934)"},
                            {"kind": "xa", "id": "0x58..0x5B by answer", "when": "step 7 answer loop (0x800EC718/0x800EC754)"},
                            {"kind": "xa_fade_out", "speed": 8, "when": "step 6 tick 2420 (0x800EC57C) and finish if still playing (0x800EBAAC)"},
                            {"kind": "sound", "id": 0x29F, "when": "step 1 tick 0 (0x800EBC80), step 6 tick 0 (0x800EC3EC)"},
                            {"kind": "sound", "id": 0x2A0, "when": "step 5 tick 0 (0x800EC1C0), finish if ctx+0xD latched (0x800EBA90)", "note": "pairs with 0x29F (latched in ctx+0xD); stop-cue semantics unverified"},
                            {"kind": "music", "note": "no music cue call in scene 5 code; finish calls SLES0x8001B7E8(-1) which stores 0xFFFF at 0x800966BA (XA/music selection reset, semantics unverified)"}],
             "camera_interpolation": {"opcodes": {"0x18": "focus interpolation: header bits16..18 = ease mode, low16 = ticks; from current focus (absolute or actor-relative) to words[1..3] (GAME0x800C174C)", "0x19": "orbit interpolation: same header layout; from current orbit (+0x58..+0x60) to words[1..3] (GAME0x800C182C)"},
                                      "ease_table": "GAME0x800DC7E0: 0 linear 0x800C1EC4, 1 cosine in-out 0x800C2114, 2 quadratic ease-out 0x800C2234, 3 quadratic ease-in 0x800C2318, 4..7 linear",
                                      "runtime_support": "native_scene.gd _commands() treats opcodes 24/25 as unknown (sets message_failed) - must be added"},
             "emulation": {"script": "tools/intro_scene.py", "native_ticks": ticks, "simulated_answers": e.answer_log, "finish_request_block": req, "cross_check": cross},
             "source": {"overlay": "DAT/ST39T.BIN (load 0x800E7000; ST3901T.BIN code region 0x30..0x1E000 byte-identical)", "handler_table": "0x800F2204 (init 0x800EB7CC, update 0x800EB960, finish 0x800EB9F4)", "dispatch": "0x800EB790",
                        "initialize": "0x800EB7CC (jump table 0x800E7048)", "update": "0x800EB960", "finish": "0x800EB9F4", "command_pointer": "0x800f1bac", "timeline_pointer": "0x800f1f14",
                        "command_interpreter": "GAME0x800C1204 (sizes verified: 0x10..0x1A=16, 0x40/0x41=8, 0x42=20, else 4; stream ends exactly at timeline)", "timeline_runner": "GAME0x800C0D70", "advance": "GAME0x800C0EA8",
                        "scene_context": "0x8007CEC0 (+2 phase,+3 step,+4/+5 handler state,+6/+7 callback substates,+0xC answer,+0xD sound latch,+0x28 step frame,+0x2C+slot*4 actor pointers,+0xAC timeline ptr,+0xB0 player face controller)",
                        "actor_class_table": "0x800ED028 (class->cell): 0x02->0x800E7370, 0x30->0x800E7594, 0x39->0x800E79E0 (variants 0x800EDB94), 0x47->0x800E8ED0, 0x63->0x800E8FCC (variants 0x800EDDD4)"}}

    contract = {"schema": 1, "stage": "ST39", "scene_id": 5,
                "source": "Original ST39T scene handler 0x800EB790 (init 0x800EB7CC, update 0x800EB960, finish 0x800EB9F4) and timeline callbacks 0x800EBB7C..0x800ECC10; actor controllers ST39T 0x800E7594/0x800E79E0/0x800E8ED0/0x800E8FCC",
                "tick_basis": "tick = native ctx+0x28 value seen by the callback (step 0 starts at 1 because init state 0 runs GAME0x800C0D70 once; other steps start at 0). A callback-driven advance (GAME0x800C0EA8) sets ctx byte0 bit 0x08 so GAME0x800C0D70 skips the camera interpreter and frame increment on that tick.",
                "initialization": {"player_position_raw": [0, 0, 0], "player_yaw_raw": 0, "player_yaw_unverified": True, "player_yaw_note": "native init does not write yaw (+0x2A); 0 is a placeholder; player render flag is cleared during the area-0 shots", "source": "0x800EB86C..0x800EB8CC", "player_state_gate": "GAME0x800CDD50()==0 (0x800EB86C)",
                                   "spawn_records": [], "spawn_note": "slot 0 (0x800f1b0c) is activated by camera opcode 0x40 at total tick 0; every other record by later 0x40 commands",
                                   "init_ops": [{"op": "camera_start", "commands": "0x800F1BAC", "timeline": "0x800F1F14", "source": "0x800EB818..0x800EB828 GAME0x800C0C5C"},
                                                {"op": "restore_call", "native": "GAME0x800C1148", "source": "0x800EB82C"},
                                                SKY(0x258, -0x300, "0x800EB83C..0x800EB84C"), VIS(False, "0x800EB850..0x800EB858"),
                                                {"op": "player_face_init", "eye_table_ram": "0x800F2018", "mouth_table_ram": "0x800F21AC", "source": "0x800EB87C..0x800EB8A8 SLES0x80041318(ctx+0xB0,...)"},
                                                EY(0, "0x800EB8B8"), MO(0, "0x800EB8C8"),
                                                {"op": "play_xa", "descriptor": 0x47, "wait_ready": True, "source": "0x800EB8D8..0x800EB944"}],
                                   "xa_start": {"descriptor_index": 0x47, "note": "timeline starts after XA 0x47 reports ready"}},
                "segments": seg, "actor_controllers": ctrl,
                "finish": {"source": "ST39T 0x800EB9F4", "fade_exit": 0x12, "fade_exit_source": "issued by step 9 at tick 250 (0x800ECBBC)",
                           "ops": [{"op": "vibration", "args_raw": [0, 0x01000000], "source": "0x800EBA54", "note": "bit24 forces the request; stops vibration (unverified)"},
                                   P(0, "0x800EBA64"), {"op": "pool_clear", "mask": 0xFFE, "flags": 0x80, "source": "0x800EBA70"}, {"op": "close_windows", "source": "0x800EBA78 SLES0x80048944(0)"},
                                   {"op": "play_sound_if_latched", "id": 0x2A0, "source": "0x800EBA80..0x800EBA98"}, {"op": "xa_fade_out", "speed": 8, "only_if_xa_ready": True, "source": "0x800EBA9C..0x800EBAB0"},
                                   {"op": "wait_xa_idle", "source": "0x800EBAC4"}],
                           "skip_path": {"source": "0x800EB9A0..0x800EB9CC", "condition": "GAME0x800C10B4() (Start pressed, ctx byte0 bits 0x20/0x04 clear, fade idle, game mode 0x203) AND scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0) then handler state 2", "unverified": "meaning of 0x1F800004 (if 0, a skip request is ignored)"},
                           "restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
                           "transition": {"destination_stage": "ST1E", "destination_area": 0, "destination_transform_raw": [0x300, -1, 0x300, 0x400], "native_transition_mode": 2, "native_entry_fade": 2, "native_exit_fade": 0xFF,
                                          "source": "0x800EBAD4..0x800EBB24 request block 0x80078D08", "request_bytes": req}},
                "xa": {"descriptor_index": 0x47, "prepare": "SLES0x8001B714", "play": "SLES0x8001B864", "ready": "SLES0x8001AF94", "descriptor_ram": xa["intro"]["descriptor_ram"], "archive": "XA/PAL_37.XA",
                       "sector_start": xa["intro"]["sector_start"], "sector_end": xa["intro"]["sector_end"], "channel": xa["intro"]["channel"], "binding_status": "descriptor decoded; audio not exported", "answers": xa["answers"]},
                "new_ops": NEW_OPS,
                "integration_notes": ["native_scene.gd _commands() rejects camera opcodes 0x18/0x19 (24/25, used 9 times) -> message_failed; add focus/orbit interpolation with the ease table", "native skips the frame increment on the tick a callback advances (ctx byte0 bit 0x08), so the next step sees tick 0; native_scene increments segment_tick after a program advance, which would skip tick-0 actions of steps 1,5,6,7,8 (callback-advanced predecessors 0,4,5,6,7)", "records span areas 0 and 1 and the scene performs three same-stage area changes; runtime spawns all records once into the starting area", "player controls 0x80..0x97 (and 1 with start_record 4) must exist in the player clip set for ST39", "opcode 0x11 targets actor slot 4 (ship 0x800f1b5c) at step 5"]}
    json.dump(scene, open(OUT + "scene_05.json", "w", encoding="utf-8"), indent=1)
    json.dump(contract, open(OUT + "scene_05_callbacks.json", "w", encoding="utf-8"), indent=1)
    json.dump({"stage": "ST39", "triggers": [{"entry_area": 0, "native_save_byte14": 0, "scene_id": 5, "source_function": "GAME0x800C0B0C", "source": "ST39T 0x800E72D8 starts scene 5 once per stage load (latch 0x80095E08) when +0x14 == 0"}]}, open(OUT + "scene_triggers.json", "w", encoding="utf-8"), indent=1)
    print(json.dumps(cross)); print("ticks", ticks, "answers", e.answer_log)

NEW_OPS = {
    "area_change": {"params": "stage, area, position_raw[3], facing_raw, fade_arrival, fade_exit, request_type(-1)", "semantics": "same-stage area change through request block 0x80078D08 (type -1, GAME0x800AEC4C); scene keeps running; player placed at position/facing", "sources": ["0x800EBBC4", "0x800EC118", "0x800EC1D8"]},
    "player_face / player_face_init": {"params": "channel eyes|mouth, sequence", "semantics": "SLES0x80041338/0x80041348 select a sequence in face controller ctx+0xB0 (tables 0x800F2018/0x800F21AC); SLES0x80041358 (called every update at 0x800EB9DC) writes the frame byte to player +0x1A0 (eyes) / +0x1A1 (mouth)", "sources": ["many, see segments"]},
    "actor_face / actor_face_init": {"params": "channel, sequence / table addresses", "semantics": "same face controller API on actor private +0x14C; actor class update (e.g. SLES0x8004152C for class 0x39) applies it", "sources": ["0x800E7BE0", "0x800E7F2C", "0x800E9230", "0x800E95DC", "0x800E897C"]},
    "player_render_flag": {"params": "set bool", "semantics": "0x8008C0A0 byte0 bit 0x02; gates SLES0x800231C8/0x80023438 player draw path (likely player visibility; unverified)", "sources": ["0x800EB850", "0x800EBC68", "0x800EBD90", "0x800EBDCC", "0x800EC1C4", "0x800EC3C4", "0x800EBB50"]},
    "sky_gradient": {"params": "horizon_raw (+0x16), param_18_raw (+0x18)", "semantics": "0x800966C0 sky gradient block; GAME0x800BEFF0 uses +0x16 as horizon base (default 0x240) when 0x800966C0 bit1 set; +0x18 consumer not found (unverified)", "sources": ["0x800EB840", "0x800EBBB8", "0x800EBC78", "0x800EBD88", "0x800EC1AC"]},
    "play_sound": {"params": "id", "semantics": "SLES0x80020160(id) non-positional sound cue (host.audio.play_sound)", "sources": ["0x800EBC80", "0x800EC1C0", "0x800EC3EC"]},
    "sound_latch / play_sound_if_latched": {"params": "value / id", "semantics": "ctx+0x0D remembers 0x29F is running; finish plays 0x2A0 when latched", "sources": ["0x800EBC8C", "0x800EC1CC", "0x800EC3FC", "0x800EBA80"]},
    "actor_state": {"params": "slot, record, field_0x0C", "semantics": "writes actor+0x0C=value,+0x0D=0 on the actor stored at ctx+0x2C+slot*4; the actor's class controller switches behaviour/control on it", "sources": ["0x800EBD40", "0x800EBEEC", "0x800EC0A8", "0x800EC548"]},
    "camera_shake": {"params": "magnitude_raw, decay_raw", "semantics": "SLES0x80016B1C(0,mag,decay) -> 0x8007D010+0xD8/+0xDC; focus Y -= (+0xD8>>8) in GAME0x800C24C0", "sources": ["0x800EBEF0"]},
    "camera_roll": {"params": "from_tick, through_tick, values_raw[]", "semantics": "0x80096D64 = camera ctx+0x14 = roll passed to SLES0x80015B6C", "sources": ["0x800EBFB8..0x800EBFF8"]},
    "vibration": {"params": "args_raw[2]", "semantics": "SLES0x80047180 pad actuator request (unverified byte meaning)", "sources": ["0x800EBF00", "0x800EBA54"]},
    "pool_clear": {"params": "mask, flags", "semantics": "SLES0x8003D658(mask,flags) clears pooled actors (as cinematics.py pool_clears)", "sources": ["0x800EBC50", "0x800EC3A0", "0x800EBA70"]},
    "close_windows": {"params": "-", "semantics": "SLES0x80048944(0) closes message windows", "sources": ["0x800EBA78"]},
    "player_axis_set / player_yaw_set / player_yaw_add": {"params": "axis, value_raw (expression of tick allowed) / yaw_raw / delta_raw", "semantics": "direct writes to player struct 0x8008C0A0 (+0x12 X integer, +0x2A yaw)", "sources": ["0x800EC60C", "0x800EC82C", "0x800ECA80", "0x800ECA84", "0x800ECB60"]},
    "play_xa / xa_fade_out / wait_xa_idle": {"params": "descriptor | descriptor_by_answer+select / speed / -", "semantics": "SLES0x8001B714 prepare, 0x8001B864 play, 0x8001AF94 ready, 0x8001BA44(speed) fade-out, 0x8001AFD0 idle", "sources": ["0x800EB8F0", "0x800EB918", "0x800EC718", "0x800EC754", "0x800EC57C", "0x800EBAAC", "0x800EC5A0", "0x800EC7A8", "0x800EBAC4"]},
    "skip_lock": {"params": "set bool", "semantics": "ctx 0x8007CEC0 byte0 bit 0x20; while set GAME0x800C10B4 ignores Start (scene skip)", "sources": ["0x800EC58C", "0x800EC848"]},
    "select_by_flags / jump_if / jump / label / wait_flag_clear / director_state": {"params": "see step 0:7", "semantics": "control flow of the step-7 question loop (ctx+7 jump table 0x800E7060)", "sources": ["0x800EC5D0..0x800EC7E8"]},
    "fade": {"params": "type, wait", "semantics": "SLES0x8001392C(type,0) screen transition; wait until 0x80078F01==0", "sources": ["0x800ECBBC", "0x800ECBE0"]},
    "actor_track": {"params": "keyframes[{step,tick,position_raw,yaw_raw}]", "semantics": "emulated actor position/yaw (16.16 raw units) of the unchanged class controllers, piecewise linear per native tick", "sources": ["class controllers"]},
    "effect_spawn": {"params": "args_raw", "semantics": "class 0x30 spawns SLES pool-8 effect actors (class 0x0F variant 4 attached at init 0x800E7674; variant 5 every 32 ticks via 0x800E7948 from position table a0, a1 bit7/low nibble params); effect visuals not decoded", "sources": ["0x800E7674", "0x800E7760", "0x800E7914"]},
    "camera opcodes 0x18/0x19": {"params": "header ease mode bits16..18, ticks low16; words[1..3] target", "semantics": "focus/orbit interpolation (see scene_05.json camera_interpolation)", "sources": ["GAME0x800C174C", "GAME0x800C182C", "GAME0x800DC7E0"]},
}

def export_audio(cue):
    import audio
    from disc import Mode2Track, cue_layout
    xa = json.load(open(OUT + "scene_05_callbacks.json", encoding="utf-8"))["xa"]; output = Path(OUT) / "audio"; output.mkdir(parents=True, exist_ok=True); bin_path, start, frames = cue_layout(cue); reader = Mode2Track(bin_path, start, frames); entries = []
    try:
        for source in [{"id": xa["descriptor_index"], **{key: xa[key] for key in ("archive", "sector_start", "sector_end", "channel")}}] + [{key: answer[key] for key in ("id", "archive", "sector_start", "sector_end", "channel")} for answer in xa["answers"]]:
            extent, size = audio.archive_record(reader, source["archive"])
            if int(source["sector_end"]) >= (size + 2047) // 2048: raise ValueError("XA descriptor exceeds its ISO file")
            item = audio.export_entry(reader, extent, source, output); item["file"] = "res://assets/levels/ST39/audio/" + Path(item["file"]).name; entries.append(item)
    finally: reader.stream.close()
    manifest = {"source": "ST39T scene 5 XA descriptors 0x800ED9AC and 0x800EDA34", "entries": entries}; (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest

if __name__ == "__main__":
    main()
