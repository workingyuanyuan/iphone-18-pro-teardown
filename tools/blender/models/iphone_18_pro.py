"""iPhone 18 Pro (physical-SIM variant) built from tools/measure/models/iphone-18-pro/measurements.json.

Exterior geometry comes from Apple's dimensional drawing (confidence A/B). Internal XY outlines
come from registered teardown images (confidence C). Everything in the thickness direction that
is not an exterior surface is an ESTIMATE (see Z below) - no source gives internal z positions.
Sub-details inside an outline (connectors, cans, screws) are illustrative.
"""
import math

import bpy
import numpy as np

from lib import Builder, circle, inset, rect, round_poly, stadium

MODEL_ID = "iphone-18-pro"
MEASUREMENTS = "tools/measure/models/iphone-18-pro/measurements.json"

COLORS = {
    "frame": "#5e1f2c", "frameInner": "#4a1822", "aluminum": "#c8c4c4", "steel": "#c9cbcf", "steelDark": "#8c8f94",
    "copper": "#c47a43", "magnet": "#7d7f84", "pcbEdge": "#b78a3c", "gold": "#d4af37", "lensRing": "#9a9ca2",
    "graphite": "#1b1b1e", "graphiteGray": "#55575c", "epoxy": "#141416", "smd": "#b39360", "smdDark": "#2b2b2e",
    "flex": "#b46a1c", "flexBlack": "#1e1e20", "plasticBlack": "#151517", "rubber": "#262628", "membrane": "#e8e8e4",
    "usbRed": "#4d1822", "flash": "#e9e4d6", "oledBlack": "#0d0d10", "lensGlass": "#07080b", "sapphire": "#141418",
}  # fmt: skip
CLASSES = {
    **{k: "metal" for k in ("frame", "frameInner", "aluminum", "steel", "steelDark", "copper", "magnet", "pcbEdge", "gold", "lensRing")},
    **{k: "matte" for k in ("graphite", "graphiteGray", "epoxy", "smd", "smdDark", "flex", "flexBlack", "plasticBlack", "rubber", "membrane", "usbRed", "flash", "oledBlack")},
    **{k: "glass" for k in ("lensGlass", "sapphire")},
}
SPECIALS = {"backGlass", "coverGlass", "screen", "coil", "pcb", "battery", "dots"}

# Thickness-direction stack. Exterior values are Apple's; the rest are estimates (unverified).
W, H, T = 71.85, 150.01, 8.75
ZB, ZF = -T / 2, 4.38  # back surface (A), cover-glass crown (A)
Z_PLATEAU, Z_LENS = ZB - 2.78, ZB - 2.78 - 2.11  # (A)
Z_GLASS_IN = ZB + 0.6  # inner face of the back glass (estimate)
Z_RECESS = -3.2  # floor of the back-glass recess (estimate)
Z_FLOOR = -2.9  # cavity floor = top of the back plate (estimate)
Z_DISP = 2.75  # underside of the display stack (estimate)
Z_VC0, Z_VC1 = 2.3, 2.6  # vapor chamber (estimate)
WALL = 2.2  # side-wall thickness below the display seat (estimate)


def join(objs):
    keep = objs[0]
    if len(objs) > 1:
        with bpy.context.temp_override(active_object=keep, object=keep, selected_objects=objs, selected_editable_objects=objs):
            bpy.ops.object.join()
    return keep


def bbox(p):
    p = np.asarray(p)
    return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())


def build(b: Builder, m: dict):
    D = m["derived"]
    I = m["internal"]
    rear, sides = m["rear"], m["sides"]
    body = np.array(D["bodyOutline"])
    off = lambda d: inset(body, d)
    P = lambda k: np.array(I[k]["polygon_mm"])
    lens = {k: v["value"] for k, v in rear["lenses"].items()}
    flash, sensor, mic = rear["flash"]["value"], rear["rearSensor"]["value"], rear["rearMic"]["value"]
    ring_r = rear["lensRingDiameter"]["value"] / 2
    back_glass = np.array(rear["outlines"]["backGlass"]["polygon"])
    coil_sheet = round_poly(P("coilSheet"), 1.0)
    mag = rear["magsafeCentre"]["value"]

    # ------------------------------------------------------------------ frame
    b.begin("frame")
    rings = [(np.array(r["points"]), r["z"]) for r in D["frameRings"]]
    rings += [(off(1.2), Z_DISP), (off(WALL), Z_DISP), (off(WALL), Z_FLOOR)]
    shell = b.loft("shell", rings, "frame", cap_first="down", cap_last="up")
    foot, top = np.array(D["plateau"]["foot"]), np.array(D["plateau"]["top"])
    prings = [(foot, ZB + 0.6)] + [(foot + (top - foot) * t, ZB + (Z_PLATEAU - ZB) * (0.5 - 0.5 * math.cos(math.pi * t))) for t in np.linspace(0, 1, 9)]
    plateau = b.loft("plateau", prings, "frame", cap_first="up", cap_last="down")
    # cut-outs: back-glass recess, lens / flash / sensor bores, USB-C, ports, SIM slot
    recess = b.prism("cut", inset(back_glass, -0.03), ZB - 0.5, Z_RECESS, "frame")
    b.cut(shell, recess)
    bores = [b.cyl("cut", x, y, 6.55, Z_LENS - 1, Z_FLOOR + 0.5, "frame", seg=40) for x, y in lens.values()]
    bores += [b.cyl("cut", *v["centre"], 3.3, Z_PLATEAU - 1, Z_FLOOR + 0.5, "frame", seg=28) for v in (flash, sensor)]
    cutter = join(bores)
    b.cut(shell, cutter, keep_cutter=True)
    b.cut(plateau, cutter)
    bot = sides["bottom"]
    usb = bot["usbC"]["value"]
    edge_cut = [b.end_pill("cut", usb["x"], 0, usb["width"], usb["height"], -H / 2 - 1, -H / 2 + 4, "frame")]
    for x in bot["portsLeft"]["value"]["x"] + bot["portsRight"]["value"]["x"]:
        edge_cut.append(b.end_pill("cut", x, 0, 1.53, 1.53, -H / 2 - 1, -H / 2 + 1.6, "frame", seg=6))
    sim = sides["left"]["simTray"]["value"]
    edge_cut.append(b.side_pill("cut", -1, sim["y"], sim["len"] + 0.08, sim["width"] + 0.08, 0, -W / 2 - 1, -W / 2 + 3.2, "frame"))
    b.cut(shell, join(edge_cut))
    # the machined inside of the housing is a darker, duller tone than the anodised outside
    inner = lambda c, n: Z_FLOOR - 0.02 <= c.z <= Z_DISP + 0.02 and abs(c.x) < W / 2 - 1.1 and abs(c.y) < H / 2 - 1.1 and (n.z > 0.5 or c.z < Z_DISP - 0.02 or abs(n.z) < 0.5)
    b.recolor(shell, "frameInner", inner)
    # dark liners behind the bottom ports so they read as holes
    for x in bot["portsLeft"]["value"]["x"] + bot["portsRight"]["value"]["x"]:
        b.end_pill("port", x, 0, 1.6, 1.6, -H / 2 + 1.3, -H / 2 + 1.6, "plasticBlack", seg=6)
    for x in bot["screws"]["value"]["x"]:
        b.end_pill("screw", x, 0, 1.5, 1.5, -H / 2 + 0.02, -H / 2 + 0.8, "steelDark", seg=8)
    # graphite film on the recess floor (seen with the back glass off)
    b.prism("film", coil_sheet, Z_RECESS - 0.04, Z_RECESS, "graphiteGray")
    # lens rings, cover glass, flash, rear sensor window, rear mic
    for name, (x, y) in lens.items():
        b.ring(f"lensRing.{name}", x, y, ring_r, 7.65, Z_LENS - 0.12, Z_PLATEAU + 0.2, "lensRing", seg=64, bevel_bottom=0.18, bevel=0)
        b.ring(f"lensCover.{name}", x, y, 7.65, 6.43, Z_LENS, Z_LENS + 0.4, "sapphire", seg=56)
        b.ring(f"lensBaffle.{name}", x, y, 6.55, 4.6, Z_LENS + 0.4, Z_LENS + 0.9, "plasticBlack", seg=40)
        b.cyl(f"lensWindow.{name}", x, y, 6.43, Z_LENS + 0.02, Z_LENS + 0.3, "lensGlass", seg=48)
    b.cyl("flashLens", *flash["centre"], flash["diameter"] / 2, Z_PLATEAU - 0.03, Z_PLATEAU + 0.4, "flash", seg=40)
    b.cyl("sensorWindow", *sensor["centre"], sensor["diameter"] / 2, Z_PLATEAU - 0.02, Z_PLATEAU + 0.4, "sapphire", seg=40)
    b.cyl("rearMic", *mic["centre"], mic["diameter"] / 2, Z_PLATEAU - 0.01, Z_PLATEAU + 0.3, "plasticBlack", seg=16)
    # buttons (left: action, volume up/down; right: side button, Camera Control)
    for k in ("actionButton", "volumeUp", "volumeDown"):
        v = sides["left"][k]["value"]
        b.side_pill(k, -1, v["y"], v["len"], v["width"], v["z"], -W / 2 + 0.6, -W / 2 - v["proud"], "frame")
    v = sides["right"]["sideButton"]["value"]
    b.side_pill("sideButton", 1, v["y"], v["len"], v["width"], v["z"], W / 2 - 0.6, W / 2 + v["proud"], "frame")
    v = sides["right"]["cameraControl"]["value"]
    b.side_pill("cameraControl", 1, v["y"], v["len"], v["width"], v["z"], W / 2 - 0.6, W / 2 + 0.03, "sapphire")
    # antenna breaks (positions from the drawing's line work; width is not drawn - 1 mm assumed)
    ab = D["antennaBreaks"]
    for y in ab["sidesY"]:
        for sx in (-1, 1):
            x = sx * W / 2
            b.box("antenna", min(x, x - sx * 0.3) - 0.02 * (sx < 0), max(x, x - sx * 0.3) + 0.02 * (sx > 0), y - 0.5, y + 0.5, -1.4, 1.45, "rubber")
    for x in ab["topBottomX"]:
        for sy in (-1, 1):
            y = sy * H / 2
            b.box("antenna", x - 0.5, x + 0.5, min(y, y - sy * 0.3) - 0.02 * (sy < 0), max(y, y - sy * 0.3) + 0.02 * (sy > 0), -1.4, 1.45, "rubber")

    # ------------------------------------------------------------------ SIM tray
    b.begin("simTray")
    b.side_pill("cap", -1, sim["y"], sim["len"], sim["width"], 0, -W / 2 + 1.6, -W / 2 - 0.01, "frame")
    b.side_pill("pinHole", -1, sim["y"] + sim["len"] / 2 - 1.6, 0.9, 0.9, 0, -W / 2 + 0.2, -W / 2 - 0.03, "plasticBlack", seg=6)
    b.box("tray", -W / 2 + 1.6, -19.6, sim["y"] - 8.2, sim["y"] + 8.2, -0.45, 0.45, "frame", r=0.6)
    b.box("sim1", -31.5, -21.0, sim["y"] - 6.2, sim["y"] + 6.2, 0.45, 0.5, "gold", r=0.8)

    # ------------------------------------------------------------------ back glass + MagSafe
    b.begin("backGlass")
    b.prism("glass", inset(back_glass, 0.04), ZB, Z_GLASS_IN, "backGlass", bevel=0, bevel_bottom=0.2)
    x0, y0 = mag
    b.prism("coil", circle(x0, y0, 22.0, 72), Z_GLASS_IN, Z_GLASS_IN + 0.25, "coil", holes=[circle(x0, y0, 8.0, 48)], uvs=(x0 - 22, y0 - 22, x0 + 22, y0 + 22))
    ro, ri = I["magnetRing"]["circle"]["r"], I["magnetRingInner"]["circle"]["r"]
    n = 18
    for i in range(n):
        a0, a1 = i / n * 2 * math.pi + 0.025, (i + 1) / n * 2 * math.pi - 0.025
        if abs(((a0 + a1) / 2) - 1.5 * math.pi) < 0.2:
            continue  # gap at the bottom of the ring where the alignment magnet sits (CT)
        th = np.linspace(a0, a1, 7)
        seg = np.vstack([np.c_[x0 + ro * np.cos(th), y0 + ro * np.sin(th)], np.c_[x0 + ri * np.cos(th[::-1]), y0 + ri * np.sin(th[::-1])]])
        b.prism("magnet", seg, Z_GLASS_IN, Z_GLASS_IN + 0.3, "magnet")
    b.box("alignMagnet", -3.0, 3.0, -52.9, -33.6, Z_GLASS_IN, Z_GLASS_IN + 0.3, "magnet", r=0.4)
    b.box("coilFlex", 14.0, 20.0, 6.0, 19.0, Z_GLASS_IN, Z_GLASS_IN + 0.08, "flex")
    b.box("coilConnector", 17.2, 28.0, 18.9, 22.4, Z_GLASS_IN, Z_GLASS_IN + 0.25, "steel", r=0.4)
    b.prism("film", coil_sheet, Z_GLASS_IN + 0.31, Z_GLASS_IN + 0.35, "graphite", extra="hide")
    b.cyl("magsafeOverlay", x0, y0, 28.75, ZB - 0.32, ZB - 0.28, "overlay.magsafe", seg=72, extra="show", overlay=True)

    # ------------------------------------------------------------------ display
    b.begin("display")
    crown = [(np.array(r["points"]), r["z"]) for r in D["glassCrownRings"]]
    b.loft("coverGlass", [(off(1.2), 3.55)] + crown, "coverGlass", cap_first="down", cap_last="up")
    act = np.array(D["activeOutline"])
    # 0.03 mm above the glass so the two faces never z-fight after position quantisation
    b.prism("screen", act, ZF + 0.02, ZF + 0.03, "screen", uvs=bbox(act), cap_bottom=False)
    b.prism("oled", off(1.5), 2.95, 3.55, "oledBlack")
    b.prism("copperLayer", off(1.8), 2.9, 2.95, "copper")
    b.prism("backPlate", off(2.3), 2.8, 2.9, "steel")
    b.box("graphite", -30.0, 30.0, -70.0, 61.0, Z_DISP, 2.8, "graphite", r=5)
    b.box("driverBracket", -14.0, 14.0, -72.6, -66.2, 2.62, Z_DISP, "steel", r=0.4)
    b.box("displayFlex", -30.5, -18.5, 13.2, 20.2, 2.62, Z_DISP, "flexBlack", r=0.5)

    # ------------------------------------------------------------------ connector covers
    b.begin("shields")
    for k in ("shields.display", "shields.battery"):
        ax0, ay0, ax1, ay1 = bbox(P(k))
        b.box("cover", ax0, ax1, ay0, ay1, 2.0, 2.5, "steel", r=0.6, bevel=0.1)
        b.cyl("screw", ax0 + 1.2, ay0 + 1.2, 0.75, 2.5, 2.58, "aluminum", seg=12)
        b.cyl("screw", ax1 - 1.2, ay1 - 1.2, 0.75, 2.5, 2.58, "aluminum", seg=12)

    # ------------------------------------------------------------------ vapor chamber
    b.begin("vc")
    vc = round_poly(P("vc"), 1.0)
    win = [round_poly(h, 0.8) for h in I["vc"].get("holes_mm", [])]
    b.prism("plate", vc, Z_VC0, Z_VC1, "steel", holes=win, bevel=0.06)
    b.prism("chamber", rect(-8.0, -52.0, 28.0, 58.0, 4.0), Z_VC1, Z_VC1 + 0.02, "steelDark", holes=[inset(w, -0.6) for w in win], cap_bottom=False)
    b.prism("sticker", inset(vc, 0.5), Z_VC1 + 0.02, Z_VC1 + 0.07, "graphite", holes=[inset(w, -0.3) for w in win], extra="hide", cap_bottom=False)
    sx0, sy0, sx1, sy1 = bbox(P("soc"))
    b.box("socPad", sx0 + 0.4, sx1 - 0.4, sy0 + 0.4, sy1 - 0.4, 1.95, Z_VC0, "aluminum", r=0.4)
    b.cyl("screw", 3.3, 37.4, 1.6, Z_VC1, Z_VC1 + 0.14, "aluminum", seg=20)
    for x, y in [(-30.8, 50.5), (28.5, 66.0), (32.3, 24.1), (30.2, -53.5), (-12.5, -55.5), (-30.5, -43.8), (-30.6, 10.8), (-30.6, 23.0)]:
        b.cyl("screw", x, y, 0.85, Z_VC1, Z_VC1 + 0.12, "aluminum", seg=12)

    # ------------------------------------------------------------------ battery
    b.begin("battery")
    bat = round_poly(P("battery"), 2.0)
    b.prism("cell", bat, Z_FLOOR, Z_VC0, "battery", bevel=0.45, uvs=bbox(bat))
    b.box("flex", 15.8, 23.8, 13.0, 17.9, 1.3, 1.5, "flexBlack")
    b.box("pullTab", -26.0, -21.0, 11.6, 13.2, 2.05, 2.15, "membrane")

    # ------------------------------------------------------------------ Face ID + front camera
    b.begin("faceId")
    ir = P("faceId.ir")
    icx, icy = (bbox(ir)[0] + bbox(ir)[2]) / 2 + 0.25, (bbox(ir)[1] + bbox(ir)[3]) / 2 + 0.1
    b.prism("irBracket", ir, 0.9, 1.4, "steel", bevel=0.08)
    b.cyl("irBarrel", icx, icy, 3.9, 1.4, 2.25, "steel", seg=8)
    b.cyl("irBody", icx, icy, 3.3, 1.4, 2.66, "plasticBlack", seg=32)
    b.cyl("irLens", icx, icy, 2.0, 2.66, 2.7, "lensGlass", seg=28)
    ax0, ay0, ax1, ay1 = bbox(P("faceId.bridge"))
    b.box("bridge", ax0, ax1, ay0, ay1, 1.9, 2.25, "steel", r=0.4)
    b.box("bridgeSlot", ax0 + 3.0, ax1 - 3.5, (ay0 + ay1) / 2 - 0.5, (ay0 + ay1) / 2 + 0.5, 2.25, 2.28, "plasticBlack", r=0.4)
    ax0, ay0, ax1, ay1 = bbox(P("faceId.dot"))
    b.box("dotProjector", ax0, ax1, ay0, ay1, 0.9, 2.55, "steel", r=0.5, bevel=0.1)
    b.box("dotWindow", ax0 + 2.3, ax1 - 1.6, ay0 + 2.4, ay1 - 2.0, 2.55, 2.6, "plasticBlack", r=0.8)
    b.cyl("dotEmitter", (ax0 + ax1) / 2 + 0.4, (ay0 + ay1) / 2 + 0.2, 1.3, 2.6, 2.64, "gold", seg=20)
    ax0, ay0, ax1, ay1 = bbox(P("faceId.front"))
    b.box("frontCamera", ax0, ax1, ay0, ay1, 0.9, 2.5, "steel", r=0.5, bevel=0.1)
    b.cyl("frontBarrel", (ax0 + ax1) / 2, (ay0 + ay1) / 2 + 0.2, 3.1, 2.5, 2.62, "plasticBlack", seg=32)
    b.cyl("frontLens", (ax0 + ax1) / 2, (ay0 + ay1) / 2 + 0.2, 2.2, 2.62, 2.68, "lensGlass", seg=28)
    b.box("flex", -12.0, -9.5, 38.5, 63.6, 2.05, 2.15, "flexBlack")
    verts = [(-45, 5, 70), (45, 5, 70), (45, 95, 70), (-45, 95, 70)]
    b.mesh("dots", verts, [(0, 1, 2, 3)], "dots", uvs=(-45, 5, 45, 95), extra="show", overlay=True)

    # ------------------------------------------------------------------ rear cameras (one unit on a steel cage)
    b.begin("rearCamera")
    mods = {"ultraWide": P("rearCamera.uw"), "main": round_poly(P("rearCamera.main"), 1.5), "tele": round_poly(P("rearCamera.tele"), 1.5)}
    for name, poly in mods.items():
        x, y = lens[name]
        b.prism(f"module.{name}", poly, -2.4, 2.0, "steelDark", bevel=0.25)
        b.prism(f"label.{name}", inset(poly, 0.9), 2.0, 2.04, "graphite", cap_bottom=False)
        b.cyl(f"barrel.{name}", x, y, 6.3, Z_LENS + 0.95, -2.4, "plasticBlack", seg=40)
        b.ring(f"barrelRim.{name}", x, y, 6.3, 4.4, Z_LENS + 0.9, Z_LENS + 0.95, "plasticBlack", seg=40)
        if name == "tele":
            b.box("frontElement.tele", x - 2.3, x + 2.3, y - 2.3, y + 2.3, Z_LENS + 0.92, Z_LENS + 1.0, "lensGlass", r=0.5)
        else:
            b.cyl(f"frontElement.{name}", x, y, 3.3, Z_LENS + 0.92, Z_LENS + 1.0, "lensGlass", seg=32)
    cage = round_poly([[-13.8, 41.6], [10.9, 41.6], [10.9, 30.0], [32.7, 30.0], [32.7, 53.0], [30.0, 53.0], [30.0, 68.8], [13.8, 68.8], [13.8, 61.8], [-13.8, 61.8]], 1.2)
    b.prism("cage", cage, -2.85, -2.4, "steel", holes=[circle(x, y, 6.9, 40) for x, y in lens.values()])
    b.box("flex", 0.5, 8.0, 38.3, 41.6, 1.2, 1.35, "flexBlack")

    # ------------------------------------------------------------------ top speaker
    b.begin("topSpeaker")
    b.prism("body", round_poly(P("topSpeaker"), 1.0), 0.2, 2.1, "plasticBlack", bevel=0.25)
    b.box("membrane", -28.6, -17.4, 41.0, 59.5, 2.1, 2.16, "steel", r=1.0)
    b.box("port", -16.6, -13.0, 63.0, 66.0, 2.1, 2.15, "steelDark", r=0.5)

    # ------------------------------------------------------------------ logic board, AP side
    b.begin("apBoard")
    board = round_poly(P("apBoard"), 1.2)
    bb = bbox(board)
    b.prism("pcb", board, 0.3, 1.1, "pcb", uvs=bb)
    b.prism("interposer", inset(board, 0.3), -0.6, 0.3, "pcbEdge", holes=[inset(board, 1.7)])
    comps = [  # [x0, x1, y0, y1, key, height] read off the 10:19 frame
        (-24.3, -22.6, 13.8, 20.7, "plasticBlack", 0.5), (-20.0, -18.7, 14.2, 19.6, "plasticBlack", 0.5),  # display connectors
        (15.6, 24.0, 17.8, 21.6, "plasticBlack", 0.5),  # battery connector
        (-29.7, -26.0, 31.3, 35.0, "epoxy", 0.6), (-25.2, -23.0, 31.3, 34.4, "epoxy", 0.6), (-22.3, -17.7, 31.2, 34.3, "epoxy", 0.6),
        (-21.5, -18.0, 21.3, 30.0, "smdDark", 0.6), (1.3, 4.7, 29.9, 34.3, "epoxy", 0.6), (0.7, 6.7, 18.3, 28.3, "epoxy", 0.6),
        (7.3, 13.7, 23.3, 28.0, "epoxy", 0.6), (7.3, 13.7, 18.7, 22.7, "epoxy", 0.6), (14.3, 22.7, 23.3, 29.0, "epoxy", 0.6), (23.0, 27.0, 25.3, 29.0, "epoxy", 0.6),
    ]  # fmt: skip
    for cx0, cx1, cy0, cy1, key, h in comps:
        b.box("component", cx0, cx1, cy0, cy1, 1.1, 1.1 + h, key, r=0.25)
    b.box("batteryContacts", 16.4, 23.2, 18.6, 20.8, 1.6, 1.63, "gold")
    b.box("bracket", -17.0, 0.3, 32.4, 35.0, 1.1, 1.85, "steel", r=0.5)
    for x, y in [(3.3, 37.4), (-28.4, 24.2), (27.9, 24.0)]:
        b.ring("standoff", x, y, 1.7, 0.8, 1.1, 1.9, "aluminum", seg=20)
    avoid = [(c[0], c[1], c[2], c[3]) for c in comps] + [(sx0, sx1, sy0, sy1), (-17.0, 0.3, 32.4, 35.0), (5.3, 31.0, 29.6, 39.0), (-1.0, 31.0, 12.0, 16.7)]
    b.smd_field("smd", bb[0] + 0.8, bb[2] - 0.8, bb[1] + 0.6, bb[3] - 0.6, 1.1, 130, "smd", avoid=avoid, seed=7)
    b.smd_field("smdDark", bb[0] + 0.8, bb[2] - 0.8, bb[1] + 0.6, bb[3] - 0.6, 1.1, 60, "smdDark", avoid=avoid, seed=11)

    b.begin("soc")
    b.box("lid", sx0, sx1, sy0, sy1, 1.1, 1.9, "chip.soc", r=0.5, uvs=(sx0, sy0, sx1, sy1), extra="hide")
    b.box("substrate", sx0, sx1, sy0, sy1, 1.1, 1.3, "pcbEdge", r=0.5, extra="show")
    die = (sx0 + 0.8, sy0 + 1.2, sx0 + 9.1, sy1 - 1.2)
    b.box("die", die[0], die[2], die[1], die[3], 1.3, 1.78, "chip.socDie", uvs=die, extra="show")
    for k, (ry0, ry1) in enumerate([(sy0 + 1.2, sy0 + 7.9), (sy1 - 7.9, sy1 - 1.2)]):
        r = (sx0 + 9.9, ry0, sx1 - 0.8, ry1)
        b.box(f"ram{k}", r[0], r[2], r[1], r[3], 1.3, 1.72, "chip.ram", uvs=r, extra="show")

    # ------------------------------------------------------------------ logic board, RF side (hidden: layout unverified)
    b.begin("rfBoard")
    b.prism("pcb", board, -1.4, -0.6, "pcb", uvs=bb)
    for cx0, cx1, cy0, cy1 in [(8.0, 14.0, 18.0, 27.0), (17.0, 28.5, 18.0, 28.0)]:
        b.box("can", cx0, cx1, cy0, cy1, -0.6, -0.1, "steel", r=0.3)
    for cx0, cx1, cy0, cy1 in [(-29.0, -21.0, 15.0, 23.0), (-14.0, -4.0, 16.0, 26.0)]:
        b.box("can", cx0, cx1, cy0, cy1, -2.0, -1.4, "steel", r=0.3)
    chips = {"modem": (-28.0, 26.5, -19.5, 35.5), "n1": (-16.0, 29.5, -9.0, 35.5), "nand": (-12.0, 16.5, -1.0, 25.5)}
    b.smd_field("smd", bb[0] + 0.8, 4.5, bb[1] + 0.6, bb[3] - 0.6, -0.6, 90, "smd", avoid=[(v[0], v[2], v[1], v[3]) for v in chips.values()], seed=5)
    for pid, (cx0, cy0, cx1, cy1) in chips.items():
        b.begin(pid)
        b.box("package", cx0, cx1, cy0, cy1, -0.6, -0.05, f"chip.{pid}", uvs=(cx0, cy0, cx1, cy1))

    # ------------------------------------------------------------------ SIM reader
    b.begin("simReader")
    ax0, ay0, ax1, ay1 = bbox(P("simReader"))
    b.box("lower", ax0, ax1, ay0, ay1, Z_FLOOR, -0.9, "steel", r=1.0)
    b.box("upper", ax0, ax1, ay0, ay1, 0.9, 1.6, "steel", r=1.0, bevel=0.1)
    b.box("spine", ax1 - 1.5, ax1, ay0 + 1.0, ay1 - 1.0, -0.9, 0.9, "steel")
    b.box("shield", ax0 + 3.5, ax1 - 2.0, ay0 + 3.6, ay1 - 4.0, 1.6, 1.65, "plasticBlack", r=0.5)

    # ------------------------------------------------------------------ bottom speaker
    b.begin("bottomSpeaker")
    b.prism("box", round_poly(P("bottomSpeaker"), 1.2), Z_FLOOR, 1.9, "plasticBlack", bevel=0.3)
    b.prism("plate", round_poly([[-27.0, -58.2], [-21.6, -52.6], [-15.6, -52.6], [-15.6, -64.0], [-27.0, -64.0]], 0.8), 1.9, 1.97, "steel", cap_bottom=False)

    # ------------------------------------------------------------------ Taptic Engine
    b.begin("taptic")
    ax0, ay0, ax1, ay1 = bbox(P("taptic"))
    b.box("body", ax0 + 0.5, ax1 - 0.5, ay0, ay1, -2.7, 1.7, "graphiteGray", r=0.8, bevel=0.3)
    b.box("capL", ax0, ax0 + 0.5, ay0 + 0.3, ay1 - 0.3, -2.2, 1.3, "steel")
    b.box("capR", ax1 - 0.5, ax1, ay0 + 0.3, ay1 - 0.3, -2.2, 1.3, "steel")

    # ------------------------------------------------------------------ bottom mic module
    b.begin("micModule")
    ax0, ay0, ax1, ay1 = bbox(P("micModule"))
    b.box("can", ax0, ax1, ay0, ay1, -1.8, 1.0, "steel", r=0.6, bevel=0.1)
    b.box("membrane", ax0 + 1.5, ax0 + 6.0, ay0 - 0.6, ay0, -1.0, 0.5, "membrane")
    b.box("baro", ax1 - 5.5, ax1 - 1.5, ay0 + 0.8, ay1 - 0.8, 1.0, 1.3, "epoxy", r=0.3)

    # ------------------------------------------------------------------ USB-C + flex (flex route is hidden: illustrative)
    b.begin("usbFlex")
    ax0, ay0, ax1, ay1 = bbox(P("usbFlex"))
    b.box("receptacle", ax0 + 0.9, ax1 - 0.9, ay0, ay1, -1.55, 1.55, "steel", r=1.0, bevel=0.3)
    b.box("flange", ax0, ax1, ay0 + 0.2, ay1, -1.55, -1.0, "steel", r=0.6)
    b.box("tongue", -3.3, 3.3, ay0 - 0.2, ay0 + 4.0, -0.35, 0.35, "usbRed")
    b.box("flexA", -7.0, 7.0, ay1, -58.2, Z_FLOOR, Z_FLOOR + 0.15, "flex")
    b.box("flexB", 7.0, 33.2, -60.4, -58.0, Z_FLOOR, Z_FLOOR + 0.15, "flex")
    b.box("flexC", 30.8, 33.2, -58.0, 17.0, Z_FLOOR, Z_FLOOR + 0.15, "flex")
    b.box("mic2", -7.0, -4.5, -65.0, -62.5, Z_FLOOR + 0.15, Z_FLOOR + 0.7, "steel")

    # ------------------------------------------------------------------ top antenna + flash (module outline unverified)
    b.begin("topAntenna")
    fx, fy = flash["centre"]
    b.prism("flex", rect(-31.5, 54.5, -14.5, 72.3, 2.0), Z_FLOOR, Z_FLOOR + 0.3, "flex")
    b.cyl("flashBody", fx, fy, 3.2, Z_PLATEAU + 0.42, Z_FLOOR + 0.3, "flash", seg=28)
    b.box("can", -31.0, -26.5, 55.2, 58.6, Z_FLOOR + 0.3, Z_FLOOR + 0.9, "steel", r=0.3)
    b.box("spring", -29.5, -15.5, 71.0, 72.4, Z_FLOOR + 0.3, -1.2, "steel")
    b.cyl("rearMicBoss", mic["centre"][0], mic["centre"][1] + 4.6, 1.0, Z_FLOOR, Z_FLOOR + 0.5, "epoxy", seg=16)

    # ------------------------------------------------------------------ LiDAR
    b.begin("lidar")
    ax0, ay0, ax1, ay1 = bbox(P("lidar"))
    sxy = sensor["centre"]
    b.box("body", ax0, ax1, ay0, ay1, Z_FLOOR, -0.6, "plasticBlack", r=1.2)
    b.box("lid", ax0 - 0.3, ax1 + 0.3, ay0 - 0.3, ay1 + 0.3, -0.6, -0.4, "steel", r=1.3)
    b.cyl("barrel", *sxy, 3.2, Z_PLATEAU + 0.42, Z_FLOOR, "plasticBlack", seg=28)
    b.box("flex", ax1, ax1 + 5.0, ay0 + 3.0, ay0 + 6.0, -0.6, -0.5, "flex")
