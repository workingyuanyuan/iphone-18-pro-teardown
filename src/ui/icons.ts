import type { Category } from '../core/types';

const svg = (body: string) =>
  `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const categoryIcon: Record<Category, string> = {
  exterior: svg('<rect x="6" y="2.5" width="12" height="19" rx="3"/>'),
  structure: svg('<rect x="6" y="2.5" width="12" height="19" rx="3"/><path d="M9 6h6"/>'),
  display: svg('<rect x="6" y="2.5" width="12" height="19" rx="3"/><rect x="8" y="5" width="8" height="14" rx="1" fill="currentColor" opacity=".35" stroke="none"/>'),
  thermal: svg('<path d="M4 8c2-2 4 2 6 0s4-2 6 0 4 2 4 0M4 13c2-2 4 2 6 0s4-2 6 0 4 2 4 0M4 18c2-2 4 2 6 0s4-2 6 0 4 2 4 0"/>'),
  power: svg('<path d="M13 2 5 14h6l-1 8 8-12h-6z"/>'),
  compute: svg('<rect x="6" y="6" width="12" height="12" rx="1.5"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>'),
  camera: svg('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>'),
  audio: svg('<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9a4 4 0 0 1 0 6M19.5 6.5a7.5 7.5 0 0 1 0 11"/>'),
  sensor: svg('<circle cx="12" cy="12" r="2"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 7.8a6 6 0 0 1 0 8.4M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>'),
  connectivity: svg('<path d="M12 12v9M8 21h8"/><path d="M8.5 8.5a5 5 0 0 1 7 0M6 6a8.5 8.5 0 0 1 12 0"/><circle cx="12" cy="11.5" r="1.2" fill="currentColor"/>'),
};

export const categoryName: Record<Category, string> = {
  exterior: '外觀',
  structure: '結構',
  display: '顯示',
  thermal: '散熱',
  power: '電力',
  compute: '運算',
  camera: '相機',
  audio: '聲音與震動',
  sensor: '感測',
  connectivity: '連接與通訊',
};

export const icon = {
  lock: svg('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
  check: svg('<path d="m5 12 4.5 4.5L19 7"/>'),
  out: svg('<path d="M12 3v12M7 8l5-5 5 5"/><path d="M5 15v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4"/>'),
  undo: svg('<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>'),
  reset: svg('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>'),
  next: svg('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  xray: svg('<rect x="6" y="2.5" width="12" height="19" rx="3" stroke-dasharray="2.5 2.5"/><rect x="9" y="8" width="6" height="8" rx="1"/>'),
  explode: svg('<rect x="3" y="9" width="7" height="7" rx="1"/><rect x="14" y="4" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'),
  zoom: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4M11 8v6M8 11h6"/>'),
  close: svg('<path d="M6 6l12 12M18 6 6 18"/>'),
  play: svg('<path d="M7 4v16l13-8z" fill="currentColor" stroke="none"/>'),
  help: svg('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.01"/>'),
  eye: svg('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  sparkle: svg('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>'),
};
