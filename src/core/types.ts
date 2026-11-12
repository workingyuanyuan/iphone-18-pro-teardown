import type { Object3D } from 'three';

/** How sure we are about a claim or a piece of geometry. */
export type Confidence = 'observed' | 'inferred' | 'approximate';

export interface SourceRef {
  /** Video timestamp, e.g. "08:56". */
  t: string;
  note?: string;
}

export interface Spec {
  label: string;
  value: string;
  source?: SourceRef;
  confidence?: Confidence;
}

export type Category =
  | 'exterior'
  | 'display'
  | 'thermal'
  | 'power'
  | 'compute'
  | 'camera'
  | 'audio'
  | 'sensor'
  | 'connectivity'
  | 'structure';

export type Side = 'front' | 'back' | 'side';

/** Optional extra visual shown while a part is selected (the video's "easter eggs"). */
export type ExtraKind = 'magsafe' | 'dotProjector' | 'peelSticker' | 'wmcm';

export interface PartDef {
  id: string;
  name: string;
  /** Short English/technical name shown under the Chinese name. */
  subtitle?: string;
  category: Category;
  /** One or two sentences: what it is and what it does, in plain language. */
  summary: string;
  facts?: { text: string; source?: SourceRef }[];
  specs?: Spec[];
  /** Geometry fidelity note shown on the info card. */
  geometry: Confidence;
  /** Parts that physically cover this one; all must be removed before it can come out. */
  blockedBy: string[];
  /** Child parts (e.g. chips) are selectable but move with their parent and are never removed alone. */
  parent?: string;
  removable: boolean;
  /** Direction (local phone space) the part travels when removed. */
  removeDir: [number, number, number];
  /** Offset (mm) applied at full explode. */
  explode: [number, number, number];
  /** Which side the camera should look from when focusing this part. */
  viewFrom: Side;
  extra?: ExtraKind;
  /** Line shown by the guided "next step" tour when this part is removed. */
  guideLine?: string;
}

export interface PhoneModel {
  id: string;
  name: string;
  /** Body size in millimetres [width, height, depth]. */
  size: [number, number, number];
  sizeNote: string;
  source: { title: string; url: string; date: string };
  parts: PartDef[];
  /** Removal order used by the guided tour (video order). */
  guideOrder: string[];
  /**
   * Load one object per part id (geometry in phone-local millimetres, +z = screen side).
   * Rejects if the model cannot be fetched or is missing a part. `onProgress` gets 0..1.
   * Materials (whose canvas textures draw text) are only created after `before` settles, so the
   * download can run while web fonts load.
   */
  load(opts?: { onProgress?: (fraction: number) => void; before?: Promise<unknown> }): Promise<Map<string, Object3D>>;
}
