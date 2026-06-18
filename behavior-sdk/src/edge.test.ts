import { describe, expect, it } from "vitest";
import { extractMobileFeatures } from "./edge.js";
import type { TouchSwipe } from "./types.js";

describe("extractMobileFeatures", () => {
  it("computes swipe_velocity_norm as the mean of hypot(vx,vy)", () => {
    const swipes: TouchSwipe[] = [
      { len: 0, dur: 0, vx: 3, vy: 4 }, // hypot = 5
      { len: 0, dur: 0, vx: 0, vy: 1 }, // hypot = 1
    ];
    const features = extractMobileFeatures(swipes);
    expect(features.swipe_velocity_norm).toBeCloseTo(3, 5); // (5+1)/2
  });

  it("computes swipe_angle_dev as population stdev of atan2(vy,vx), only when >1 swipe", () => {
    const single: TouchSwipe[] = [{ len: 0, dur: 0, vx: 1, vy: 0 }];
    expect(extractMobileFeatures(single).swipe_angle_dev).toBeUndefined();

    const swipes: TouchSwipe[] = [
      { len: 0, dur: 0, vx: 1, vy: 0 }, // angle 0
      { len: 0, dur: 0, vx: 0, vy: 1 }, // angle pi/2
    ];
    const angles = [0, Math.PI / 2];
    const m = (angles[0]! + angles[1]!) / 2;
    const expected = Math.sqrt(((angles[0]! - m) ** 2 + (angles[1]! - m) ** 2) / 2);
    expect(extractMobileFeatures(swipes).swipe_angle_dev).toBeCloseTo(expected, 10);
  });

  it("computes touch_pressure_avg as the mean of pressure samples", () => {
    const features = extractMobileFeatures([], [0.2, 0.4, 0.6]);
    expect(features.touch_pressure_avg).toBeCloseTo(0.4, 10);
  });

  it("computes acceleration_variance as the population variance of motion magnitude", () => {
    const features = extractMobileFeatures([], [], [
      { x: 1, y: 0, z: 0 },
      { x: 3, y: 0, z: 0 },
    ]);
    // magnitudes [1,3], mean=2, pvariance = ((1-2)^2+(3-2)^2)/2 = 1
    expect(features.acceleration_variance).toBeCloseTo(1, 10);
  });

  it("omits dims it has no samples for, rather than defaulting to 0 itself", () => {
    const features = extractMobileFeatures([]);
    expect(features).toEqual({});
  });
});
