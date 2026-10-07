import { describe, expect, it } from "vitest";

import { BAND_FILL, BAND_SWATCH, BAND_WORDS, COMFORTABLE, GETTING_THERE, band } from "./mastery";

describe("mastery bands", () => {
  it("words a score by where it falls, with null meaning not rated (which is not a low score)", () => {
    expect(band(null)).toBe("none");
    expect(band(0)).toBe("needs-work");
    expect(band(GETTING_THERE - 0.0001)).toBe("needs-work");
    expect(band(GETTING_THERE)).toBe("getting-there");
    expect(band(COMFORTABLE - 0.0001)).toBe("getting-there");
    expect(band(COMFORTABLE)).toBe("comfortable");
    expect(band(1)).toBe("comfortable");
  });

  it("has the same thresholds as the server's rule and a word and two colours for every band", () => {
    expect([COMFORTABLE, GETTING_THERE]).toEqual([0.67, 0.4]); // api/learner/mastery.py
    for (const b of ["none", "comfortable", "getting-there", "needs-work"] as const) {
      expect(BAND_WORDS[b]).toBeTruthy();
      expect(BAND_FILL[b]).toMatch(/^fill-/);
      expect(BAND_SWATCH[b]).toMatch(/^bg-/);
    }
    expect(new Set(Object.values(BAND_FILL)).size).toBe(4);
  });
});
