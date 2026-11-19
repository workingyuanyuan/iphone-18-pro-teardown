/**
 * Plain metadata for the iPhone 18 Pro, kept free of three.js and `import.meta.env` so the build
 * config (vite.config.ts, which writes the static text into index.html) can import it in Node.
 */
export const W = 71.85;
export const H = 150.01;
export const D = 8.75;

export const meta = {
  id: 'iphone-18-pro',
  name: 'iPhone 18 Pro',
  size: [W, H, D] as [number, number, number],
  sizeNote: '外觀依 Apple 官方尺寸圖建模，內部零件位置依拆解影像量測。',
  source: {
    title: 'iPhone 18 Pro 系列拆解：這才叫「系統級」散熱設計！【享拆】— 微機分 WekiHome',
    url: 'https://youtu.be/BLKegH19KGI',
    date: '2026-09-20',
  },
};
