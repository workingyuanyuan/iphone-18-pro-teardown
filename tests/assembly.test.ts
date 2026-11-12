import { describe, expect, it } from 'vitest';
import { Assembly, validateParts } from '../src/core/assembly';
import type { PartDef } from '../src/core/types';
import { parts, guideOrder } from '../src/data/phones/iphone-18-pro/parts';

const p = (id: string, blockedBy: string[] = [], extra: Partial<PartDef> = {}): PartDef => ({
  id,
  name: id,
  category: 'structure',
  summary: '',
  geometry: 'approximate',
  blockedBy,
  removable: true,
  removeDir: [0, 0, 1],
  explode: [0, 0, 0],
  viewFrom: 'front',
  ...extra,
});

// screen covers vc, vc covers battery and board.
const fixture = [p('frame', [], { removable: false }), p('screen'), p('vc', ['screen']), p('battery', ['vc']), p('board', ['vc']), p('chip', [], { parent: 'board', removable: false })];

describe('Assembly', () => {
  it('only exposed parts can be removed', () => {
    const a = new Assembly(fixture);
    expect(a.canRemove('screen')).toBe(true);
    expect(a.canRemove('vc')).toBe(false);
    expect(a.blockersOf('battery')).toEqual(['vc']);
    expect(a.canRemove('frame')).toBe(false);
  });

  it('planRemove removes covering parts first', () => {
    const a = new Assembly(fixture);
    expect(a.planRemove('battery').map((s) => s.id)).toEqual(['screen', 'vc', 'battery']);
  });

  it('planInstall lifts covering parts and restores them', () => {
    const a = new Assembly(fixture);
    for (const s of a.planRemove('battery')) a.apply(s);
    a.apply({ op: 'install', id: 'vc' });
    a.apply({ op: 'install', id: 'screen' });
    const plan = a.planInstall('battery');
    expect(plan).toEqual([
      { op: 'remove', id: 'screen' },
      { op: 'remove', id: 'vc' },
      { op: 'install', id: 'battery' },
      { op: 'install', id: 'vc' },
      { op: 'install', id: 'screen' },
    ]);
    for (const s of plan) a.apply(s);
    expect(a.removedIds()).toEqual([]);
  });

  it('lifts transitively when an intermediate cover is already out', () => {
    const a = new Assembly(fixture);
    for (const s of a.planRemove('battery')) a.apply(s);
    a.apply({ op: 'install', id: 'screen' }); // screen back on while vc is out
    const plan = a.planInstall('battery');
    for (const s of plan) a.apply(s);
    expect(a.isInstalled('battery')).toBe(true);
    expect(a.isInstalled('screen')).toBe(true);
    expect(a.isInstalled('vc')).toBe(false);
  });

  it('planInstallAll restores everything in a legal order', () => {
    const a = new Assembly(fixture);
    for (const id of ['screen', 'vc', 'board', 'battery']) a.apply({ op: 'remove', id });
    for (const s of a.planInstallAll()) a.apply(s);
    expect(a.removedIds()).toEqual([]);
  });

  it('planInstallAll lifts covers that were reinstalled early', () => {
    const a = new Assembly(fixture);
    for (const s of a.planRemove('battery')) a.apply(s);
    a.apply({ op: 'install', id: 'screen' }); // screen back on, vc + battery still out
    for (const s of a.planInstallAll()) a.apply(s);
    expect(a.removedIds()).toEqual([]);
  });

  it('child parts follow their parent', () => {
    const a = new Assembly(fixture);
    expect(a.isInstalled('chip')).toBe(true);
    for (const s of a.planRemove('board')) a.apply(s);
    expect(a.isInstalled('chip')).toBe(false);
  });

  it('validateParts finds cycles and unknown ids', () => {
    const bad = [p('a', ['b']), p('b', ['a']), p('c', ['zzz'])];
    const kinds = validateParts(bad, ['a', 'b', 'c']).map((i) => i.kind);
    expect(kinds).toContain('cycle');
    expect(kinds).toContain('missing');
  });
});

describe('iPhone 18 Pro data', () => {
  it('has a valid graph and guided order', () => {
    expect(validateParts(parts, guideOrder)).toEqual([]);
  });

  it('every removable part can be removed and reinstalled from any single-removal state', () => {
    for (const target of parts.filter((x) => x.removable)) {
      const a = new Assembly(parts);
      for (const s of a.planRemove(target.id)) a.apply(s);
      expect(a.isInstalled(target.id)).toBe(false);
      for (const s of a.planInstallAll()) a.apply(s);
      expect(a.removedIds()).toEqual([]);
    }
  });
});
