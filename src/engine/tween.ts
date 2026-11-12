export type Ease = (t: number) => number;
export const easeInOut: Ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOut: Ease = (t) => 1 - Math.pow(1 - t, 3);

interface Tween {
  t: number;
  dur: number;
  ease: Ease;
  update: (k: number) => void;
  resolve: () => void;
  key?: string;
}

/** Minimal tween runner driven by the render loop. Tweens with the same key replace each other. */
export class Tweens {
  private list: Tween[] = [];
  /** Global duration multiplier (reduced motion). */
  speed = 1;

  get active(): boolean {
    return this.list.length > 0;
  }

  run(dur: number, update: (k: number) => void, opts: { ease?: Ease; key?: string } = {}): Promise<void> {
    if (opts.key) this.cancel(opts.key);
    return new Promise((resolve) => {
      const d = dur * this.speed;
      if (d <= 0) {
        update(1);
        resolve();
        return;
      }
      this.list.push({ t: 0, dur: d, ease: opts.ease ?? easeInOut, update, resolve, key: opts.key });
    });
  }

  cancel(key: string): void {
    this.list = this.list.filter((tw) => {
      if (tw.key !== key) return true;
      tw.resolve();
      return false;
    });
  }

  tick(dt: number): void {
    if (!this.list.length) return;
    const done: Tween[] = [];
    for (const tw of this.list) {
      tw.t = Math.min(tw.dur, tw.t + dt);
      tw.update(tw.ease(tw.t / tw.dur));
      if (tw.t >= tw.dur) done.push(tw);
    }
    if (done.length) {
      this.list = this.list.filter((tw) => !done.includes(tw));
      for (const tw of done) tw.resolve();
    }
  }
}
