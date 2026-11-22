// Scene colors; they match the CSS tokens in styles.css (palette of albusxiao.dev).
export const SCENE = {
  /** ink-950, outside the world. */
  background: 0x05070a,
  /** ink-850, the world ground. */
  ground: 0x0b0f15,
  /** Hairline color shared by `line` (#94aac81c) and `line-strong` (#94aac838). */
  line: 0x94aac8,
  lineOpacity: 0x1c / 0xff,
  lineStrongOpacity: 0x38 / 0xff,
  /** signal. */
  mover: 0x6fd6f7,
  /** wire. */
  selection: 0xa8e6ff,
} as const;
