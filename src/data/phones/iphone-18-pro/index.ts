import type { PhoneModel } from '../../../core/types';
import { meta } from './meta';
import { loadIphone18Pro } from './model';
import { parts, guideOrder } from './parts';

export const iphone18Pro: PhoneModel = {
  ...meta,
  parts,
  guideOrder,
  load: loadIphone18Pro,
};
