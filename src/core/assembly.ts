import type { PartDef } from './types';

/** One atomic animation step. */
export interface Step {
  op: 'remove' | 'install';
  id: string;
}

/**
 * Pure assembly logic: which parts are installed, what blocks what, and the
 * step plans for removing / reinstalling parts. No three.js here so it can be unit tested.
 */
export class Assembly {
  readonly parts: Map<string, PartDef>;
  private installed: Set<string>;
  /** Reverse edges: part -> parts it covers. */
  private covers = new Map<string, string[]>();

  constructor(parts: PartDef[]) {
    this.parts = new Map(parts.map((p) => [p.id, p]));
    this.installed = new Set(parts.filter((p) => p.removable).map((p) => p.id));
    for (const p of parts) {
      for (const b of p.blockedBy) {
        const list = this.covers.get(b) ?? [];
        list.push(p.id);
        this.covers.set(b, list);
      }
    }
  }

  isInstalled(id: string): boolean {
    const p = this.parts.get(id);
    if (!p) return false;
    if (!p.removable) return p.parent ? this.isInstalled(p.parent) : true;
    return this.installed.has(id);
  }

  installedIds(): string[] {
    return [...this.installed];
  }

  removedIds(): string[] {
    return [...this.parts.values()].filter((p) => p.removable && !this.installed.has(p.id)).map((p) => p.id);
  }

  /** Installed parts that currently cover `id`. */
  blockersOf(id: string): string[] {
    const p = this.parts.get(id);
    if (!p) return [];
    return p.blockedBy.filter((b) => this.installed.has(b));
  }

  canRemove(id: string): boolean {
    const p = this.parts.get(id);
    return !!p && p.removable && this.installed.has(id) && this.blockersOf(id).length === 0;
  }

  /** Steps to remove `id`, first removing everything that covers it (deepest blockers first). */
  planRemove(id: string): Step[] {
    const p = this.parts.get(id);
    if (!p || !p.removable || !this.installed.has(id)) return [];
    const order: string[] = [];
    const seen = new Set<string>();
    const visit = (x: string) => {
      if (seen.has(x)) return;
      seen.add(x);
      for (const b of this.parts.get(x)!.blockedBy) if (this.installed.has(b)) visit(b);
      order.push(x);
    };
    visit(id);
    return order.map((x) => ({ op: 'remove', id: x }));
  }

  /**
   * Steps to put `id` back. Parts that would cover it and are currently installed are lifted
   * out first and restored afterwards, so the user is never blocked.
   */
  planInstall(id: string): Step[] {
    const p = this.parts.get(id);
    if (!p || !p.removable || this.installed.has(id)) return [];
    // Installed parts that sit above `id` (transitively through covering relations).
    const lifted: string[] = [];
    const seen = new Set<string>();
    const collect = (x: string) => {
      for (const b of this.parts.get(x)!.blockedBy) {
        if (seen.has(b)) continue;
        seen.add(b);
        collect(b);
        if (this.installed.has(b)) lifted.push(b);
      }
    };
    collect(id);
    // Remove outermost first: a part can only be removed once its own blockers are out.
    const removeOrder = this.topoRemoveOrder(lifted);
    return [
      ...removeOrder.map((x): Step => ({ op: 'remove', id: x })),
      { op: 'install', id },
      ...[...removeOrder].reverse().map((x): Step => ({ op: 'install', id: x })),
    ];
  }

  /**
   * Install everything that is missing. Installed parts that cover a missing part are lifted
   * out first, then everything goes back innermost first.
   */
  planInstallAll(): Step[] {
    const missing = this.removedIds();
    const lifted = new Set<string>();
    const seen = new Set<string>();
    const collect = (x: string) => {
      for (const b of this.parts.get(x)!.blockedBy) {
        if (seen.has(b)) continue;
        seen.add(b);
        collect(b);
        if (this.installed.has(b)) lifted.add(b);
      }
    };
    for (const id of missing) collect(id);
    const liftOrder = this.topoRemoveOrder([...lifted]);
    const installOrder = this.topoRemoveOrder([...missing, ...lifted]).reverse();
    return [
      ...liftOrder.map((id): Step => ({ op: 'remove', id })),
      ...installOrder.map((id): Step => ({ op: 'install', id })),
    ];
  }

  /** Order a set of parts so each comes after all of its blockers (valid removal order). */
  private topoRemoveOrder(ids: string[]): string[] {
    const set = new Set(ids);
    const out: string[] = [];
    const done = new Set<string>();
    const visit = (x: string) => {
      if (done.has(x)) return;
      done.add(x);
      for (const b of this.parts.get(x)!.blockedBy) if (set.has(b)) visit(b);
      out.push(x);
    };
    for (const id of ids) visit(id);
    return out;
  }

  /** Apply one step. Throws if it violates the physical constraints. */
  apply(step: Step): void {
    if (step.op === 'remove') {
      if (!this.canRemove(step.id)) throw new Error(`cannot remove ${step.id}`);
      this.installed.delete(step.id);
    } else {
      const p = this.parts.get(step.id);
      if (!p || !p.removable || this.installed.has(step.id)) throw new Error(`cannot install ${step.id}`);
      if (this.blockersOf(step.id).length) throw new Error(`${step.id} is covered`);
      this.installed.add(step.id);
    }
  }

  /** Parts directly covered by `id` (used for hints like "拆下後可看到…"). */
  revealedBy(id: string): string[] {
    return this.covers.get(id) ?? [];
  }

  /** Next step of the guided tour: first part in tour order that is still installed. */
  nextGuided(order: string[]): Step[] {
    const next = order.find((id) => this.installed.has(id));
    return next ? this.planRemove(next) : [];
  }
}

export interface ValidationIssue {
  kind: 'missing' | 'cycle' | 'parent' | 'guide' | 'duplicate';
  message: string;
}

/** Validate a part graph: unknown ids, cycles, parents, and the guided order. */
export function validateParts(parts: PartDef[], guideOrder: string[]): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const ids = new Map<string, PartDef>();
  for (const p of parts) {
    if (ids.has(p.id)) issues.push({ kind: 'duplicate', message: `duplicate id ${p.id}` });
    ids.set(p.id, p);
  }
  for (const p of parts) {
    for (const b of p.blockedBy) {
      if (!ids.has(b)) issues.push({ kind: 'missing', message: `${p.id} blockedBy unknown ${b}` });
      else if (!ids.get(b)!.removable) issues.push({ kind: 'missing', message: `${p.id} blockedBy non-removable ${b}` });
    }
    if (p.parent && !ids.has(p.parent)) issues.push({ kind: 'parent', message: `${p.id} has unknown parent ${p.parent}` });
    if (p.parent && p.removable) issues.push({ kind: 'parent', message: `${p.id} has a parent but is removable` });
  }
  // Cycle detection.
  const state = new Map<string, 0 | 1 | 2>();
  const dfs = (id: string, path: string[]): void => {
    const s = state.get(id) ?? 0;
    if (s === 2) return;
    if (s === 1) {
      issues.push({ kind: 'cycle', message: `cycle: ${[...path, id].join(' -> ')}` });
      return;
    }
    state.set(id, 1);
    for (const b of ids.get(id)?.blockedBy ?? []) if (ids.has(b)) dfs(b, [...path, id]);
    state.set(id, 2);
  };
  for (const p of parts) dfs(p.id, []);
  // Guided order must remove every removable part, each one legal at its turn.
  const removable = parts.filter((p) => p.removable).map((p) => p.id);
  const missing = removable.filter((id) => !guideOrder.includes(id));
  if (missing.length) issues.push({ kind: 'guide', message: `guide order misses ${missing.join(', ')}` });
  if (!issues.some((i) => i.kind === 'cycle' || i.kind === 'missing')) {
    const a = new Assembly(parts);
    for (const id of guideOrder) {
      if (!a.canRemove(id)) {
        issues.push({ kind: 'guide', message: `guide step ${id} is blocked by ${a.blockersOf(id).join(', ') || '?'}` });
        break;
      }
      a.apply({ op: 'remove', id });
    }
  }
  return issues;
}
