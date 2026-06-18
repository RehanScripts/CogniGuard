import type { TouchSwipe } from "./types.js";

export interface MotionSample {
  x: number;
  y: number;
  z: number;
}

function mean(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

/** Population variance/stdev (denominator N, not N-1) — matches Python's
 * `statistics.pvariance`/`pstdev` used by gateway/app/services/feature_reader.py. */
function pvariance(values: number[]): number {
  const m = mean(values);
  return mean(values.map((v) => (v - m) ** 2));
}

function pstdev(values: number[]): number {
  return Math.sqrt(pvariance(values));
}

/**
 * Mobile edge feature extraction (NFR-10): raw touch/sensor streams never leave the
 * device — only this derived feature vector is sent, folding into `derived_features`.
 * `swipe_velocity_norm`/`swipe_angle_dev` use the same formulas as
 * `feature_reader.py::_behavior_from_payload`'s web-path reduction so a mobile-derived
 * value means the same thing as a server-reduced one. `touch_pressure_avg` and
 * `acceleration_variance` have no raw-web-contract equivalent — mobile-only.
 */
export function extractMobileFeatures(
  swipes: readonly TouchSwipe[],
  pressureSamples: readonly number[] = [],
  motionSamples: readonly MotionSample[] = [],
): Record<string, number> {
  const features: Record<string, number> = {};

  if (swipes.length > 0) {
    features.swipe_velocity_norm = mean(swipes.map((s) => Math.hypot(s.vx, s.vy)));
    if (swipes.length > 1) {
      features.swipe_angle_dev = pstdev(swipes.map((s) => Math.atan2(s.vy, s.vx)));
    }
  }

  if (pressureSamples.length > 0) {
    features.touch_pressure_avg = mean([...pressureSamples]);
  }

  if (motionSamples.length > 0) {
    const magnitudes = motionSamples.map((m) => Math.hypot(m.x, m.y, m.z));
    features.acceleration_variance = pvariance(magnitudes);
  }

  return features;
}
