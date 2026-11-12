import type { PhoneModel } from '../../../core/types';
import { loadIphone18Pro, W, H, D } from './model';
import { parts, guideOrder } from './parts';

export const iphone18Pro: PhoneModel = {
  id: 'iphone-18-pro',
  name: 'iPhone 18 Pro',
  size: [W, H, D],
  sizeNote: '外觀依 Apple 官方尺寸圖建模，內部零件位置依拆解影像量測。',
  source: {
    title: 'iPhone 18 Pro 系列拆解：這才叫「系統級」散熱設計！【享拆】— 微機分 WekiHome',
    url: 'https://youtu.be/BLKegH19KGI',
    date: '2026-09-20',
  },
  parts,
  guideOrder,
  load: loadIphone18Pro,
};
