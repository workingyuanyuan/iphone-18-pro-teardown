import { CanvasTexture, RepeatWrapping, SRGBColorSpace, type Texture } from 'three';

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return [c, c.getContext('2d')!];
}

function tex(c: HTMLCanvasElement, srgb = true): Texture {
  const t = new CanvasTexture(c);
  if (srgb) t.colorSpace = SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

/** Lock-screen style wallpaper with clock and a small Dynamic Island. */
export function wallpaper(): Texture {
  const [c, g] = canvas(512, 1024);
  const grd = g.createLinearGradient(0, 0, 512, 1024);
  grd.addColorStop(0, '#2b0f1a');
  grd.addColorStop(0.45, '#7a2338');
  grd.addColorStop(1, '#f0a36b');
  g.fillStyle = grd;
  g.fillRect(0, 0, 512, 1024);
  for (let i = 0; i < 5; i++) {
    const r = g.createRadialGradient(80 + i * 90, 600 + (i % 2) * 180, 0, 80 + i * 90, 600 + (i % 2) * 180, 260);
    r.addColorStop(0, 'rgba(255,200,170,0.22)');
    r.addColorStop(1, 'rgba(255,200,170,0)');
    g.fillStyle = r;
    g.fillRect(0, 0, 512, 1024);
  }
  g.fillStyle = 'rgba(255,255,255,0.92)';
  g.textAlign = 'center';
  g.font = '500 30px -apple-system, "Noto Sans TC", sans-serif';
  g.fillText('11月6日 星期五', 256, 170);
  g.font = '600 150px -apple-system, "SF Pro Display", "Noto Sans TC", sans-serif';
  g.fillText('9:41', 256, 320);
  // Dynamic Island.
  g.fillStyle = '#000';
  // Size and position from Apple's drawing: 15.66 × 6.07 mm, centred 5.35 mm below the top of the
  // 66.57 × 144.73 mm active area (this texture spans exactly the active area).
  const w = (15.66 / 66.57) * 512,
    h = (6.07 / 144.73) * 1024,
    x = 256 - w / 2,
    y = (5.355 / 144.73) * 1024 - h / 2;
  g.beginPath();
  g.roundRect(x, y, w, h, h / 2);
  g.fill();
  // Home indicator.
  g.fillStyle = 'rgba(255,255,255,0.85)';
  g.beginPath();
  g.roundRect(256 - 70, 990, 140, 8, 4);
  g.fill();
  return tex(c);
}

/** Regulatory label printed on the battery can. */
export function batteryLabel(): Texture {
  const [c, g] = canvas(512, 640);
  g.fillStyle = '#c9cbce';
  g.fillRect(0, 0, 512, 640);
  // Brushed noise.
  for (let i = 0; i < 1600; i++) {
    g.fillStyle = `rgba(${Math.random() < 0.5 ? '255,255,255' : '0,0,0'},${Math.random() * 0.05})`;
    g.fillRect(0, Math.random() * 640, 512, 1);
  }
  g.fillStyle = 'rgba(40,40,44,0.75)';
  g.font = '600 22px "Noto Sans TC", sans-serif';
  g.fillText('Li-ion Battery  鋰離子電池', 40, 70);
  g.font = '16px monospace';
  const lines = ['3.90V  4056mAh  15.855Wh', 'Rated capacity', 'Made in China', 'Cell: ATL', 'A3xxx  616-xxxxx', '警告：請勿拆解、擠壓或加熱'];
  lines.forEach((l, i) => g.fillText(l, 40, 110 + i * 26));
  // Certification icons (generic shapes).
  g.lineWidth = 3;
  g.strokeStyle = 'rgba(40,40,44,0.7)';
  for (let i = 0; i < 5; i++) {
    g.beginPath();
    if (i % 2) g.arc(70 + i * 70, 330, 22, 0, Math.PI * 2);
    else g.strokeRect(48 + i * 70, 308, 44, 44);
    g.stroke();
  }
  // Fine print + QR-ish block.
  g.font = '11px sans-serif';
  for (let i = 0; i < 8; i++) g.fillText('Caution: risk of fire and burns. Do not open, crush, heat above 60°C.'.slice(0, 40 + (i % 3) * 8), 40, 400 + i * 16);
  for (let y = 0; y < 12; y++) for (let x = 0; x < 12; x++) if (Math.random() > 0.5) g.fillRect(400 + x * 6, 540 + y * 6, 6, 6);
  return tex(c);
}

/** Laser-etched chip marking. */
export function chipLabel(lines: string[], bg = '#141416', fg = 'rgba(200,200,205,0.75)'): Texture {
  const [c, g] = canvas(256, 256);
  g.fillStyle = bg;
  g.fillRect(0, 0, 256, 256);
  g.fillStyle = fg;
  g.font = '600 34px -apple-system, sans-serif';
  g.textAlign = 'center';
  lines.forEach((l, i) => {
    g.font = i === 0 ? '600 38px -apple-system, sans-serif' : '22px monospace';
    g.fillText(l, 128, 110 + i * 40);
  });
  g.beginPath();
  g.arc(28, 28, 8, 0, Math.PI * 2);
  g.fill();
  return tex(c);
}

/** Bright brushed metal lid (SoC heat spreader / shields). */
export function brushed(base = '#bfc2c6'): Texture {
  const [c, g] = canvas(256, 256);
  g.fillStyle = base;
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 900; i++) {
    g.fillStyle = `rgba(${Math.random() < 0.5 ? '255,255,255' : '0,0,0'},${Math.random() * 0.06})`;
    g.fillRect(Math.random() * 256, 0, 1, 256);
  }
  const t = tex(c);
  t.wrapS = t.wrapT = RepeatWrapping;
  return t;
}

/** PCB solder mask with traces and via dots. */
export function pcb(): Texture {
  const [c, g] = canvas(512, 512);
  g.fillStyle = '#18231d';
  g.fillRect(0, 0, 512, 512);
  g.strokeStyle = 'rgba(80,120,90,0.35)';
  g.lineWidth = 2;
  for (let i = 0; i < 120; i++) {
    let x = Math.random() * 512,
      y = Math.random() * 512;
    g.beginPath();
    g.moveTo(x, y);
    for (let k = 0; k < 4; k++) {
      if (Math.random() < 0.5) x += (Math.random() - 0.5) * 120;
      else y += (Math.random() - 0.5) * 120;
      g.lineTo(x, y);
    }
    g.stroke();
  }
  g.fillStyle = 'rgba(200,170,90,0.6)';
  for (let i = 0; i < 400; i++) g.fillRect(Math.random() * 512, Math.random() * 512, 2, 2);
  const t = tex(c);
  t.wrapS = t.wrapT = RepeatWrapping;
  return t;
}

/** Copper coil striations for the wireless charging coil (applied radially via UV). */
export function coil(): Texture {
  const [c, g] = canvas(64, 512);
  for (let y = 0; y < 512; y += 4) {
    g.fillStyle = y % 8 ? '#a8622c' : '#d08a4a';
    g.fillRect(0, y, 64, 4);
  }
  const t = tex(c);
  t.wrapS = t.wrapT = RepeatWrapping;
  return t;
}

/** Glowing near-infrared dot pattern (Face ID easter egg). */
export function dotPattern(): Texture {
  const [c, g] = canvas(512, 512);
  g.fillStyle = 'rgba(0,0,0,0)';
  g.clearRect(0, 0, 512, 512);
  for (let y = 0; y < 22; y++)
    for (let x = 0; x < 22; x++) {
      const px = 30 + x * 21 + (y % 2) * 10 + (Math.random() - 0.5) * 4;
      const py = 30 + y * 21 + (Math.random() - 0.5) * 4;
      const d = Math.hypot(px - 256, py - 256) / 256;
      if (d > 1) continue;
      const r = g.createRadialGradient(px, py, 0, px, py, 7);
      r.addColorStop(0, `rgba(140,255,180,${0.95 - d * 0.5})`);
      r.addColorStop(1, 'rgba(60,255,140,0)');
      g.fillStyle = r;
      g.fillRect(px - 7, py - 7, 14, 14);
    }
  return tex(c);
}

/** Soft radial shadow blob for the floor. */
export function shadowBlob(): Texture {
  const [c, g] = canvas(256, 256);
  const r = g.createRadialGradient(128, 128, 10, 128, 128, 128);
  r.addColorStop(0, 'rgba(0,0,0,0.55)');
  r.addColorStop(0.6, 'rgba(0,0,0,0.18)');
  r.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = r;
  g.fillRect(0, 0, 256, 256);
  return tex(c);
}

/** Speaker/mesh grille dots. */
export function grille(): Texture {
  const [c, g] = canvas(128, 128);
  g.fillStyle = '#222326';
  g.fillRect(0, 0, 128, 128);
  g.fillStyle = '#0a0a0b';
  for (let y = 4; y < 128; y += 8) for (let x = 4 + ((y / 8) % 2) * 4; x < 128; x += 8) {
    g.beginPath();
    g.arc(x, y, 2.4, 0, Math.PI * 2);
    g.fill();
  }
  const t = tex(c);
  t.wrapS = t.wrapT = RepeatWrapping;
  return t;
}

/** Concentric copper windings for the wireless-charging coil (planar UV over the coil's bounding square). */
export function coilRadial(): Texture {
  const [c, g] = canvas(512, 512);
  g.fillStyle = '#6b3a18';
  g.fillRect(0, 0, 512, 512);
  for (let r = 256; r > 60; r -= 5) {
    g.beginPath();
    g.arc(256, 256, r, 0, Math.PI * 2);
    g.lineWidth = 3.4;
    g.strokeStyle = (r / 5) % 2 ? '#d38b4c' : '#b46c34';
    g.stroke();
  }
  return tex(c);
}
